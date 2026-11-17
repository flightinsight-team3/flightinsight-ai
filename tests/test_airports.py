"""Unit tests for the DS03 airports template. No network, no Azure: transform() is pure pandas.

Rows are built in the exact string format of the real OurAirports CSV
(trimmed, non-empty strings; empty values are "").
"""

import pandas as pd

from etl import airports

# Test time zones (real ones come from airportsdata).
TZ = {
    "LGA": "America/New_York",
    "ORD": "America/Chicago",
    "LAX": "America/Los_Angeles",
    "JFK": "America/New_York",
    "SEA": "America/Los_Angeles",
    "BOS": "America/New_York",
}


def row(**overrides: str) -> dict[str, str]:
    """One large US airport (LGA); override any field."""
    base = {column: "" for column in airports.RAW_COLUMNS}
    base.update(
        ident="KLGA",
        type="large_airport",
        name="La Guardia Airport",
        latitude_deg="40.777199",
        longitude_deg="-73.872597",
        iso_country="US",
        iso_region="US-NY",
        municipality="New York",
        iata_code="LGA",
        icao_code="KLGA",
    )
    base.update(overrides)
    return base


def run(*rows: dict[str, str], month_key: int = 202611) -> airports.TransformResult:
    return airports.transform(pd.DataFrame(list(rows)), month_key, airport_tz=TZ)


def test_normal_airport_row_is_cleaned():
    result = run(row())
    clean = result.airports.iloc[0]
    assert clean["snapshot_key"] == 202611
    assert clean["iata_code"] == "LGA"
    assert clean["icao_code"] == "KLGA"
    assert clean["airport_name"] == "La Guardia Airport"
    assert clean["city"] == "New York"
    assert clean["state_code"] == "NY"
    assert clean["latitude"] == 40.777199
    assert clean["longitude"] == -73.872597
    assert clean["timezone"] == "America/New_York"
    assert clean["hub_type"] == "large"
    assert bool(clean["is_top30"]) is True
    assert result.stats == {
        "rows_read": 1,
        "rows_out_of_scope": 0,
        "rows_clean": 1,
        "rows_rejected": 0,
        "rows_geography": 51,
    }


def test_non_us_airport_is_out_of_scope_not_rejected():
    result = run(row(), row(iso_country="CA", iso_region="CA-ON", iata_code="YYZ"))
    assert result.stats["rows_out_of_scope"] == 1
    assert len(result.airports) == 1
    assert len(result.rejected) == 0


def test_heliport_or_closed_airport_is_out_of_scope():
    result = run(row(), row(type="heliport"), row(type="closed"))
    assert result.stats["rows_out_of_scope"] == 2
    assert len(result.airports) == 1


def test_us_airport_without_iata_is_out_of_scope():
    result = run(row(), row(iata_code=""))
    assert result.stats["rows_out_of_scope"] == 1
    assert len(result.rejected) == 0


def test_invalid_rows_are_rejected_with_a_reason():
    # Each row uses a 3-letter uppercase IATA so the length/format checks don't shadow
    # downstream checks, except for the two rows that specifically test length/format.
    result = run(
        row(iata_code="LG"),                        # bad length
        row(iata_code="lg1"),                       # bad format
        row(iata_code="LAX", latitude_deg="abc"),   # bad latitude
        row(iata_code="JFK", longitude_deg="500"),  # bad longitude
        row(iata_code="ORD", iso_region="XX"),      # bad iso_region
        row(iata_code="BOS", iso_region="US-ZZ"),   # unknown state_code
        row(iata_code="XYZ"),                       # unknown IATA time zone (not in TZ)
        row(iata_code="SEA", name=""),              # missing name
    )
    assert len(result.airports) == 0
    assert sorted(result.rejected["reason"]) == sorted(
        [
            "bad iata_code length",
            "bad iata_code format",
            "bad latitude",
            "bad longitude",
            "bad iso_region",
            "unknown state_code",
            "unknown IATA time zone",
            "missing name",
        ]
    )
    assert set(result.rejected.columns) == {"source", "month_key", "reason", "raw_record"}


def test_duplicate_iata_keeps_the_first_row():
    result = run(row(name="First"), row(ident="KLG2", icao_code="KLG2", name="Second"))
    assert len(result.airports) == 1
    assert result.airports.iloc[0]["airport_name"] == "First"
    assert list(result.rejected["reason"]) == ["duplicate iata_code"]


def test_icao_falls_back_to_ident_when_empty():
    clean = run(row(icao_code="", ident="KLGA")).airports.iloc[0]
    assert clean["icao_code"] == "KLGA"


def test_icao_is_null_when_not_four_letters():
    clean = run(row(icao_code="", ident="X42")).airports.iloc[0]
    assert pd.isna(clean["icao_code"])


def test_is_top30_flag_tracks_the_config_list():
    # BOS is in TOP30_AIRPORTS, SEA is also, LGA is also. Use a non-top30 airport known in TZ.
    # Our test TZ has JFK (top30=True). All our fixtures are top30. Verify both ways:
    top30 = run(
        row(ident="KBOS", type="large_airport", name="Boston",
            iata_code="BOS", icao_code="KBOS", iso_region="US-MA", municipality="Boston"),
    ).airports.iloc[0]
    assert bool(top30["is_top30"]) is True

    # Patch TZ with a non-top30 airport to verify the flag can also be False.
    df = pd.DataFrame([row(
        ident="KPDX", type="large_airport", name="Portland Intl",
        iata_code="PDX", icao_code="KPDX", iso_region="US-OR", municipality="Portland",
        latitude_deg="45.589", longitude_deg="-122.595",
    )])
    tz = dict(TZ)
    tz["PDX"] = "America/Los_Angeles"
    result = airports.transform(df, 202611, airport_tz=tz)
    assert len(result.airports) == 1
    assert bool(result.airports.iloc[0]["is_top30"]) is False


def test_clean_columns_match_staging_table():
    result = run(row())
    assert list(result.airports.columns) == airports.STG_AIRPORT_COLUMNS
    assert list(result.geography.columns) == airports.STG_GEOGRAPHY_COLUMNS


def test_geography_has_fifty_states_plus_dc():
    geography = run(row()).geography
    assert len(geography) == 51
    assert set(geography["state_code"]) >= {"NY", "CA", "TX", "DC", "AK", "HI"}
    assert (geography["snapshot_key"] == 202611).all()
    # Census regions are exactly the four Bureau regions.
    assert set(geography["census_region"]) == {"Northeast", "Midwest", "South", "West"}


def test_empty_optional_fields_become_none():
    clean = run(row(municipality="")).airports.iloc[0]
    assert pd.isna(clean["city"])


def test_read_raw_handles_real_file_layout():
    header = ",".join(airports.RAW_COLUMNS) + "\n"
    values = ",".join(row()[c] for c in airports.RAW_COLUMNS) + "\n"
    raw = airports.read_raw((header + values).encode("utf-8"))
    assert list(raw.columns) == airports.RAW_COLUMNS
    assert raw.loc[0, "iata_code"] == "LGA"
    assert raw.loc[0, "icao_code"] == "KLGA"
