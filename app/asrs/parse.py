"""Turn a NASA ASRS Database Online CSV export into asrs_reports documents (without vectors).

The export has two header rows: a group row ("Time", "Place", "Aircraft 1", "Report 1", ...)
and a field row ("Date", "Locale Reference", "Make Model Name", "Narrative", ...). Columns are
found by field name, preferring the expected group, so repeated names such as "Narrative" in
Report 1 and Report 2 or "Flight Phase" in Aircraft 1 and Aircraft 2 are told apart.
Multi-valued cells are separated by ";".

Output documents follow cosmos/schemas/asrs_report.schema.json, minus narrative_vector.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from app.asrs.embeddings import DOCUMENT_PREFIX

# (group, field) of each column we read. The group is a preference, not a requirement.
ACN = ("", "ACN")
DATE = ("Time", "Date")
LOCALE = ("Place", "Locale Reference")
WEATHER = ("Environment", "Weather Elements / Visibility")
MAKE_MODEL = ("Aircraft 1", "Make Model Name")
FLIGHT_PHASE = ("Aircraft 1", "Flight Phase")
REPORTER = ("Person 1", "Function")
ANOMALY = ("Events", "Anomaly")
SYNOPSIS = ("Report 1", "Synopsis")
NARRATIVE_FIELD = "Narrative"

REQUIRED = (ACN, DATE)
DEIDENTIFIED = "ZZZ"  # ASRS placeholder for a location removed to protect the reporter


@dataclass
class ParseResult:
    documents: list[dict] = field(default_factory=list)
    rejected: Counter[str] = field(default_factory=Counter)


class Columns:
    """Column positions resolved from the header row(s)."""

    def __init__(self, groups: list[str], fields: list[str]):
        self.headers = [(g.strip(), f.strip()) for g, f in zip(groups, fields, strict=True)]

    def find(self, wanted: tuple[str, str]) -> int | None:
        group, name = (part.lower() for part in wanted)
        matches = [i for i, (_, f) in enumerate(self.headers) if f.lower() == name]
        in_group = [i for i in matches if self.headers[i][0].lower() == group]
        return (in_group or matches or [None])[0]

    def find_all(self, name: str) -> list[int]:
        return [i for i, (_, f) in enumerate(self.headers) if f.lower() == name.lower()]


def read_rows(path: Path) -> tuple[Columns, Iterator[list[str]]]:
    """Open the export and resolve its header (two rows, or one row of plain field names)."""
    handle = path.open(encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.reader(handle)
    first = next(reader, None)
    if first is None:
        raise ValueError(f"{path} is empty")
    if first and first[0].strip().upper() == "ACN":
        columns = Columns([""] * len(first), first)
    else:
        second = next(reader, None) or []
        width = max(len(first), len(second))
        groups = _forward_fill(_pad(first, width))
        columns = Columns(groups, _pad(second, width))

    missing = [f"{g} / {f}".strip(" /") for g, f in REQUIRED if columns.find((g, f)) is None]
    if not columns.find_all(NARRATIVE_FIELD):
        missing.append("Report 1 / Narrative")
    if missing:
        handle.close()
        found = ", ".join(f"{g} / {f}".strip(" /") for g, f in columns.headers if f)
        raise ValueError(f"Missing ASRS columns: {', '.join(missing)}. Found: {found}")

    def rows() -> Iterator[list[str]]:
        with handle:
            yield from reader

    return columns, rows()


def parse_export(path: Path) -> ParseResult:
    """Parse every report in the export. Bad rows are counted by reason, not raised."""
    columns, rows = read_rows(path)
    result = ParseResult()
    seen: set[str] = set()
    for row in rows:
        if not any(cell.strip() for cell in row):
            continue
        doc, reason = to_document(row, columns)
        if doc is None:
            result.rejected[reason] += 1
        elif doc["id"] in seen:
            result.rejected["duplicate_acn"] += 1
        else:
            seen.add(doc["id"])
            result.documents.append(doc)
    return result


def to_document(row: list[str], columns: Columns) -> tuple[dict | None, str]:
    """One CSV row → (document, "") or (None, rejection reason)."""

    def cell(wanted: tuple[str, str]) -> str:
        i = columns.find(wanted)
        return row[i].strip() if i is not None and i < len(row) else ""

    acn = cell(ACN)
    if not acn.isdigit():
        return None, "missing_acn"
    month_key = parse_month(cell(DATE))
    if month_key is None:
        return None, "bad_date"
    narratives = [row[i].strip() for i in columns.find_all(NARRATIVE_FIELD) if i < len(row)]
    narrative = "\n\n".join(n for n in narratives if n)
    if not narrative:
        return None, "missing_narrative"

    return {
        "id": acn,
        "month_key": month_key,
        "airport_code": airport_code(cell(LOCALE)),
        "aircraft_family": aircraft_family(cell(MAKE_MODEL)),
        "flight_phase": split_multi(cell(FLIGHT_PHASE)),
        "weather": split_multi(cell(WEATHER)),
        "reporter": reporter(cell(REPORTER)),
        "anomaly": split_multi(cell(ANOMALY)),
        "synopsis": cell(SYNOPSIS),
        "narrative": narrative,
    }, ""


def embedding_text(doc: dict) -> str:
    """Text that is embedded for a report: prefix + synopsis + narrative."""
    body = "\n\n".join(part for part in (doc["synopsis"], doc["narrative"]) if part)
    return DOCUMENT_PREFIX + body


def parse_month(value: str) -> int | None:
    """ASRS dates are yyyymm ("202403"). Returns None if the value is not a valid month."""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 6:
        return None
    year, month = int(digits[:4]), int(digits[4:6])
    return year * 100 + month if 2000 <= year <= 2100 and 1 <= month <= 12 else None


def split_multi(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def airport_code(locale: str) -> str | None:
    """Airport code from a locale: "ORD.Airport" or "ORD.Tower" → "ORD".

    ASRS de-identifies some locations as "ZZZ"; those, foreign ICAO codes ("CYYZ"), ARTCCs
    ("ZAU.ARTCC") and TRACONs → None."""
    first = split_multi(locale)[:1]
    match = re.fullmatch(r"K?([A-Z0-9]{3})\.(?:Airport|Tower)", first[0]) if first else None
    if not match or match.group(1) == DEIDENTIFIED:
        return None
    return match.group(1)


def aircraft_family(make_model: str) -> str | None:
    """Group ASRS make/model names into families used for filtering (B737, A320, CRJ, ERJ...)."""
    text = make_model.upper()
    if match := re.search(r"\b([AB])[- ]?(\d{3})", text):
        return match.group(1) + match.group(2)
    if "CRJ" in text or "REGIONAL JET" in text:
        return "CRJ"
    if "ERJ" in text or "EMBRAER" in text or re.search(r"\bEMB\b", text):
        return "ERJ"
    if "DASH 8" in text or "DHC-8" in text or "Q400" in text:
        return "DHC8"
    if re.search(r"\b(MD-?\d{2}|DC-?9)", text):
        return "MD80"
    return None


def reporter(function: str) -> str | None:
    """First reporter's role: "Flight Crew : Captain; Flight Crew : Pilot Flying" → "Captain"."""
    first = split_multi(function)[:1]
    if not first:
        return None
    return first[0].split(":")[-1].strip() or None


def _pad(values: list[str], width: int) -> list[str]:
    return values + [""] * (width - len(values))


def _forward_fill(groups: list[str]) -> list[str]:
    """Header groups may only be written over the first column of each group."""
    filled, current = [], ""
    for i, group in enumerate(groups):
        current = group.strip() or (current if i else "")
        filled.append(current)
    return filled
