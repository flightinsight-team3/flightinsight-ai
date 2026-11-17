"""DS03 · Airport reference data (OurAirports + a static US state table).

Follows the same template as BTS (see docs/etl-template.md):

    download(month_key)            raw CSV bytes exactly as published            (network)
    read_raw(raw)                  DataFrame of strings, nothing interpreted     (pure)
    validate(df, tz)               one rejection reason per row, "" = valid      (pure)
    transform(raw, month_key)      clean airports + geography + rejected rows    (pure)
    ingest_month(month_key, sink)  runs the steps, writes raw/ and clean/ files  (Azure or local)

Unlike BTS/NOAA this source is a snapshot, not a monthly file. `month_key` is used purely as
a snapshot version (yyyymm the snapshot was taken) so the Data Lake layout matches every other
source and ADF can re-run a single step.

Output in the Data Lake, container `clean`, folder airports/<yyyymm>/:
    airports.parquet    one row per US airport with an IATA; columns match dbo.stg_airports
    geography.parquet   one row per US state / DC;           columns match dbo.stg_geography
    rejected.parquet    rows that failed validation;          columns match dbo.stg_rejected

Geography is built from a small static table embedded below, not downloaded. There is no public
Census file that is both tiny and stable, and 50 states + DC don't change.
"""

from __future__ import annotations

import io
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from etl.config import CLEAN_CONTAINER, RAW_CONTAINER, TOP30_AIRPORTS
from etl.storage import LakeSink, Sink, to_parquet_bytes

SOURCE = "airports"
URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

# The 10 of OurAirports's 18 columns we use.
RAW_COLUMNS = [
    "ident",
    "type",
    "name",
    "latitude_deg",
    "longitude_deg",
    "iso_country",
    "iso_region",
    "municipality",
    "iata_code",
    "icao_code",
]

REQUIRED_COLUMNS = ["ident", "type", "name", "iso_country", "iata_code"]

# Only commercial-service airport types reach the star schema; heliports, seaplane bases
# and closed airports are out of scope (counted, not rejected).
AIRPORT_TYPES = {"large_airport", "medium_airport", "small_airport"}

# OurAirports type → dim_airports.hub_type bucket.
HUB_TYPE = {
    "large_airport": "large",
    "medium_airport": "medium",
    "small_airport": "small",
}

# Same columns, same order as dbo.stg_airports.
STG_AIRPORT_COLUMNS = [
    "snapshot_key",
    "iata_code",
    "icao_code",
    "airport_name",
    "city",
    "state_code",
    "latitude",
    "longitude",
    "timezone",
    "hub_type",
    "is_top30",
]

# Same columns, same order as dbo.stg_geography.
STG_GEOGRAPHY_COLUMNS = [
    "snapshot_key",
    "state_code",
    "state_name",
    "state_fips",
    "census_region",
]

# 50 states + DC. FIPS from Census; census_region from the U.S. Census Bureau's four regions.
_STATES_RAW: tuple[tuple[str, str, str, str], ...] = (
    ("AL", "Alabama", "01", "South"),
    ("AK", "Alaska", "02", "West"),
    ("AZ", "Arizona", "04", "West"),
    ("AR", "Arkansas", "05", "South"),
    ("CA", "California", "06", "West"),
    ("CO", "Colorado", "08", "West"),
    ("CT", "Connecticut", "09", "Northeast"),
    ("DE", "Delaware", "10", "South"),
    ("DC", "District of Columbia", "11", "South"),
    ("FL", "Florida", "12", "South"),
    ("GA", "Georgia", "13", "South"),
    ("HI", "Hawaii", "15", "West"),
    ("ID", "Idaho", "16", "West"),
    ("IL", "Illinois", "17", "Midwest"),
    ("IN", "Indiana", "18", "Midwest"),
    ("IA", "Iowa", "19", "Midwest"),
    ("KS", "Kansas", "20", "Midwest"),
    ("KY", "Kentucky", "21", "South"),
    ("LA", "Louisiana", "22", "South"),
    ("ME", "Maine", "23", "Northeast"),
    ("MD", "Maryland", "24", "South"),
    ("MA", "Massachusetts", "25", "Northeast"),
    ("MI", "Michigan", "26", "Midwest"),
    ("MN", "Minnesota", "27", "Midwest"),
    ("MS", "Mississippi", "28", "South"),
    ("MO", "Missouri", "29", "Midwest"),
    ("MT", "Montana", "30", "West"),
    ("NE", "Nebraska", "31", "Midwest"),
    ("NV", "Nevada", "32", "West"),
    ("NH", "New Hampshire", "33", "Northeast"),
    ("NJ", "New Jersey", "34", "Northeast"),
    ("NM", "New Mexico", "35", "West"),
    ("NY", "New York", "36", "Northeast"),
    ("NC", "North Carolina", "37", "South"),
    ("ND", "North Dakota", "38", "Midwest"),
    ("OH", "Ohio", "39", "Midwest"),
    ("OK", "Oklahoma", "40", "South"),
    ("OR", "Oregon", "41", "West"),
    ("PA", "Pennsylvania", "42", "Northeast"),
    ("RI", "Rhode Island", "44", "Northeast"),
    ("SC", "South Carolina", "45", "South"),
    ("SD", "South Dakota", "46", "Midwest"),
    ("TN", "Tennessee", "47", "South"),
    ("TX", "Texas", "48", "South"),
    ("UT", "Utah", "49", "West"),
    ("VT", "Vermont", "50", "Northeast"),
    ("VA", "Virginia", "51", "South"),
    ("WA", "Washington", "53", "West"),
    ("WV", "West Virginia", "54", "South"),
    ("WI", "Wisconsin", "55", "Midwest"),
    ("WY", "Wyoming", "56", "West"),
)

US_STATES: tuple[dict[str, str], ...] = tuple(
    {"state_code": code, "state_name": name, "state_fips": fips, "census_region": region}
    for code, name, fips, region in _STATES_RAW
)


def raw_path(month_key: int) -> str:
    return f"{SOURCE}/{month_key}/airports.csv"


def clean_path(month_key: int, table: str) -> str:
    return f"{SOURCE}/{month_key}/{table}.parquet"


@dataclass
class TransformResult:
    airports: pd.DataFrame
    geography: pd.DataFrame
    rejected: pd.DataFrame
    stats: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------- download / read
def download(month_key: int, *, retries: int = 3, timeout: int = 120, verify: bool = True) -> bytes:
    """Download the OurAirports CSV. Small (~10 MB) but mirror can hiccup, so retry."""
    import requests

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(URL, timeout=timeout, verify=verify)
            response.raise_for_status()
            if b"iata_code" not in response.content[:4096]:
                raise ValueError("OurAirports CSV is missing the expected header")
            return response.content
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(5 * attempt)
    raise RuntimeError(
        f"OurAirports download failed for {month_key} after {retries} tries: {last_error}"
    )


def read_raw(raw: bytes) -> pd.DataFrame:
    """Read the CSV as strings, keeping empty values (no NaN)."""
    df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
    missing = [c for c in RAW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"OurAirports CSV is missing columns: {missing}")
    return df[RAW_COLUMNS]


@lru_cache(maxsize=1)
def load_airport_timezones() -> dict[str, str]:
    """IATA code → IANA time zone, e.g. 'LGA' → 'America/New_York'."""
    import airportsdata

    return {code: info["tz"] for code, info in airportsdata.load("IATA").items() if info.get("tz")}


# ---------------------------------------------------------------------------- validate
def validate(df: pd.DataFrame, airport_tz: Mapping[str, str]) -> pd.Series:
    """Return one reason per row ("" = valid). The first failing rule wins."""
    reasons = pd.Series("", index=df.index, dtype=object)

    def flag(mask: pd.Series, reason: str) -> None:
        reasons.loc[mask & (reasons == "")] = reason

    for column in REQUIRED_COLUMNS:
        flag(df[column] == "", f"missing {column}")

    flag(df["iata_code"].str.len() != 3, "bad iata_code length")
    flag(~df["iata_code"].str.fullmatch(r"[A-Z]{3}").fillna(False), "bad iata_code format")

    latitude = pd.to_numeric(df["latitude_deg"], errors="coerce")
    longitude = pd.to_numeric(df["longitude_deg"], errors="coerce")
    flag(latitude.isna() | (latitude.abs() > 90), "bad latitude")
    flag(longitude.isna() | (longitude.abs() > 180), "bad longitude")

    # iso_region is like "US-NY"; state code = the last two letters.
    flag(~df["iso_region"].str.fullmatch(r"US-[A-Z]{2}").fillna(False), "bad iso_region")
    known_state = {s["state_code"] for s in US_STATES}
    state_code = df["iso_region"].str.slice(3, 5)
    flag(~state_code.isin(known_state), "unknown state_code")

    flag(df["iata_code"].str.upper().map(airport_tz).isna(), "unknown IATA time zone")
    return reasons


# ---------------------------------------------------------------------------- transform
def _rejected_rows(df: pd.DataFrame, reasons: pd.Series, month_key: int) -> pd.DataFrame:
    records = df.to_dict(orient="records")
    return pd.DataFrame(
        {
            "source": SOURCE,
            "month_key": month_key,
            "reason": reasons.to_numpy(),
            "raw_record": [json.dumps(r, ensure_ascii=False) for r in records],
        },
        columns=["source", "month_key", "reason", "raw_record"],
    )


def _build_airports(
    df: pd.DataFrame, month_key: int, airport_tz: Mapping[str, str]
) -> pd.DataFrame:
    iata = df["iata_code"].str.upper()
    # Some small airports leave icao_code empty; fall back to ident (holds ICAO for US airports).
    icao = df["icao_code"].where(df["icao_code"] != "", df["ident"])
    icao = icao.where(icao.str.fullmatch(r"[A-Z0-9]{4}").fillna(False), None)

    clean = pd.DataFrame(
        {
            "snapshot_key": month_key,
            "iata_code": iata,
            "icao_code": icao,
            "airport_name": df["name"],
            "city": df["municipality"].where(df["municipality"] != "", None),
            "state_code": df["iso_region"].str.slice(3, 5),
            "latitude": pd.to_numeric(df["latitude_deg"]).round(6),
            "longitude": pd.to_numeric(df["longitude_deg"]).round(6),
            "timezone": iata.map(airport_tz),
            "hub_type": df["type"].map(HUB_TYPE),
            "is_top30": iata.isin(TOP30_AIRPORTS),
        },
        index=df.index,
    )
    return clean[STG_AIRPORT_COLUMNS]


def _build_geography(month_key: int) -> pd.DataFrame:
    rows = [{"snapshot_key": month_key, **state} for state in US_STATES]
    return pd.DataFrame(rows, columns=STG_GEOGRAPHY_COLUMNS)


def transform(
    raw: pd.DataFrame, month_key: int, airport_tz: Mapping[str, str] | None = None
) -> TransformResult:
    """Scope, validate and clean the OurAirports snapshot. Pure: no network, no Azure."""
    tz = airport_tz if airport_tz is not None else load_airport_timezones()
    df = raw[RAW_COLUMNS].apply(lambda column: column.astype(str).str.strip())

    in_scope = (
        (df["iso_country"] == "US")
        & (df["iata_code"] != "")
        & df["type"].isin(AIRPORT_TYPES)
    )
    df = df[in_scope]

    reasons = validate(df, tz)
    valid = reasons == ""
    airports = _build_airports(df[valid], month_key, tz)

    duplicate = airports.duplicated("iata_code", keep="first")
    duplicate_index = airports.index[duplicate]
    reasons.loc[duplicate_index] = "duplicate iata_code"
    airports = airports[~duplicate].reset_index(drop=True)

    bad = reasons != ""
    rejected = _rejected_rows(df[bad], reasons[bad], month_key)
    geography = _build_geography(month_key)

    stats = {
        "rows_read": int(len(raw)),
        "rows_out_of_scope": int((~in_scope).sum()),
        "rows_clean": int(len(airports)),
        "rows_rejected": int(len(rejected)),
        "rows_geography": int(len(geography)),
    }
    return TransformResult(airports=airports, geography=geography, rejected=rejected, stats=stats)


# ---------------------------------------------------------------------------- run
def ingest_month(
    month_key: int, sink: Sink | None = None, raw: bytes | None = None
) -> dict:
    """Download (unless raw is given), keep the raw CSV, write airports/geography/rejected parquet.

    Re-running a snapshot_key overwrites its files, so it never creates duplicates.
    """
    sink = sink if sink is not None else LakeSink()
    if raw is None:
        verify = os.getenv("OURAIRPORTS_VERIFY_SSL", "true").lower() != "false"
        raw = download(month_key, verify=verify)

    raw_location = sink.write_bytes(RAW_CONTAINER, raw_path(month_key), raw)
    result = transform(read_raw(raw), month_key)
    airports_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "airports"), to_parquet_bytes(result.airports)
    )
    geography_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "geography"), to_parquet_bytes(result.geography)
    )
    rejected_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "rejected"), to_parquet_bytes(result.rejected)
    )
    return {
        "source": SOURCE,
        "month_key": month_key,
        **result.stats,
        "raw_file": raw_location,
        "airports_file": airports_location,
        "geography_file": geography_location,
        "rejected_file": rejected_location,
    }
