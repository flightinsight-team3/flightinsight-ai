"""Unit tests for ASRS export parsing. No network: files are written to tmp_path.

The fixture mimics the ASRS Database Online CSV export: a group header row, a field header
row, then one report per row with ";"-separated multi-valued cells.
"""

import csv
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.asrs import parse

SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "cosmos/schemas/asrs_report.schema.json").read_text()
)

GROUPS = [
    "", "Time", "Place", "Environment", "Aircraft 1", "Aircraft 1", "Aircraft 2",
    "Person 1", "Person 2", "Events", "Report 1", "Report 1", "Report 2", "Report 1",
]  # fmt: skip
FIELDS = [
    "ACN", "Date", "Locale Reference", "Weather Elements / Visibility", "Make Model Name",
    "Flight Phase", "Flight Phase", "Function", "Function", "Anomaly", "Narrative",
    "Callback", "Narrative", "Synopsis",
]  # fmt: skip


def report(**overrides: str) -> list[str]:
    """One ORD taxi incident; override any field by its FIELDS name (Narrative = Report 1)."""
    values = {
        "ACN": "2087654",
        "Date": "202403",
        "Locale Reference": "ORD.Airport",
        "Weather Elements / Visibility": "Snow; Ice",
        "Make Model Name": "B737-800",
        "Flight Phase": "Taxi",
        "Function": "Flight Crew : Captain; Flight Crew : Pilot Not Flying",
        "Anomaly": "Deviation - Procedural Clearance; Ground Incursion Taxiway",
        "Narrative": "We were rushed to push back because of the delay.",
        "Synopsis": "B737 Captain reported a taxiway incursion while under time pressure.",
    }
    values.update(overrides)
    row = []
    for group, name in zip(GROUPS, FIELDS, strict=True):
        if name in ("Flight Phase", "Function") and group in ("Aircraft 2", "Person 2"):
            row.append("Cruise" if name == "Flight Phase" else "ATC : Ground")
        elif name == "Narrative" and group == "Report 2":
            row.append(values.get("Narrative 2", ""))
        else:
            row.append(values.get(name, ""))
    return row


def write_export(tmp_path: Path, rows: list[list[str]], headers=(GROUPS, FIELDS)) -> Path:
    path = tmp_path / "asrs.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows([*headers, *rows])
    return path


def test_parses_report_into_schema_shape(tmp_path):
    result = parse.parse_export(write_export(tmp_path, [report()]))

    assert result.rejected == {}
    assert result.documents == [
        {
            "id": "2087654",
            "month_key": 202403,
            "airport_code": "ORD",
            "aircraft_family": "B737",
            "flight_phase": ["Taxi"],
            "weather": ["Snow", "Ice"],
            "reporter": "Captain",
            "anomaly": ["Deviation - Procedural Clearance", "Ground Incursion Taxiway"],
            "synopsis": "B737 Captain reported a taxiway incursion while under time pressure.",
            "narrative": "We were rushed to push back because of the delay.",
        }
    ]


def test_document_with_vector_matches_cosmos_schema(tmp_path):
    doc = parse.parse_export(write_export(tmp_path, [report()])).documents[0]
    doc["narrative_vector"] = [0.1] * 768

    errors = list(Draft202012Validator(SCHEMA).iter_errors(doc))
    assert not errors, [e.message for e in errors]


def test_second_report_narrative_is_appended(tmp_path):
    rows = [report(**{"Narrative 2": "First officer's account."})]
    doc = parse.parse_export(write_export(tmp_path, rows)).documents[0]
    assert doc["narrative"].endswith("\n\nFirst officer's account.")


def test_group_header_written_once_per_group_is_forward_filled(tmp_path):
    sparse = [g if i == 0 or g != GROUPS[i - 1] else "" for i, g in enumerate(GROUPS)]
    doc = parse.parse_export(write_export(tmp_path, [report()], (sparse, FIELDS))).documents[0]
    assert doc["flight_phase"] == ["Taxi"]  # Aircraft 1, not Aircraft 2
    assert doc["reporter"] == "Captain"


def test_single_header_row_is_accepted(tmp_path):
    header = ["ACN", "Date", "Narrative", "Synopsis"]
    path = write_export(tmp_path, [["1", "202401", "Text.", "Syn."]], (header,))
    assert parse.parse_export(path).documents[0]["month_key"] == 202401


def test_bad_rows_are_counted_not_raised(tmp_path):
    rows = [
        report(),
        report(),  # duplicate ACN
        report(ACN="2000001", Date="2024"),
        report(ACN="2000002", Narrative=""),
        report(ACN=""),
        [""] * len(FIELDS),  # blank line: ignored
    ]
    result = parse.parse_export(write_export(tmp_path, rows))

    assert len(result.documents) == 1
    assert result.rejected == {
        "duplicate_acn": 1,
        "bad_date": 1,
        "missing_narrative": 1,
        "missing_acn": 1,
    }


def test_missing_required_column_is_reported(tmp_path):
    path = write_export(tmp_path, [], (["", "Time"], ["ACN", "Date"]))
    with pytest.raises(ValueError, match="Narrative"):
        parse.parse_export(path)


def test_embedding_text_has_document_prefix():
    doc = {"synopsis": "Syn.", "narrative": "Story."}
    assert parse.embedding_text(doc) == "search_document: Syn.\n\nStory."


@pytest.mark.parametrize(
    "locale,expected",
    [
        ("ORD.Airport", "ORD"),
        ("KSEA.Airport", "SEA"),
        ("BZN.Tower", "BZN"),
        ("ZZZ.Airport", None),  # de-identified
        ("ZZZZ.Airport", None),
        ("ZZZ.Tower", None),
        ("CYYZ.Airport", None),  # foreign ICAO
        ("ZAU.ARTCC", None),
        ("", None),
    ],
)
def test_airport_code(locale, expected):
    assert parse.airport_code(locale) == expected


@pytest.mark.parametrize(
    "make_model,expected",
    [
        ("B737-800", "B737"),
        ("B737 Next Generation Undifferentiated", "B737"),
        ("A320", "A320"),
        ("Regional Jet 900 (CRJ900)", "CRJ"),
        ("Embraer ERJ 170/175 ER/LR", "ERJ"),
        ("Dash 8-400", "DHC8"),
        ("MD-88", "MD80"),
        ("Commercial Fixed Wing", None),
        ("", None),
    ],
)
def test_aircraft_family(make_model, expected):
    assert parse.aircraft_family(make_model) == expected


@pytest.mark.parametrize(
    "value,expected", [("202403", 202403), ("2024-03", 202403), ("202413", None), ("", None)]
)
def test_parse_month(value, expected):
    assert parse.parse_month(value) == expected
