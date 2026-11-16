"""DS01 · BTS On-Time Performance (Reporting Carrier), one month at a time.

This module is the template every data source follows (see docs/etl-template.md):

    download(month_key)            raw bytes exactly as published               (network)
    read_raw(raw)                  DataFrame of strings, nothing interpreted     (pure)
    validate(df, month_key, tz)    one rejection reason per row, "" = valid      (pure)
    transform(raw_df, month_key)   clean rows + rejected rows + counts           (pure)
    ingest_month(month_key, sink)  runs the steps, writes raw/ and clean/ files  (Azure or local)

Output in the Data Lake, container `clean`, folder bts/<yyyymm>/:
    flights.parquet    one row per in-scope flight; columns match dbo.stg_flights
    rejected.parquet   rows that failed validation; columns match dbo.stg_rejected

Times. BTS reports every time in the local time of its airport. Only the origin's time zone is
needed, because BTS also gives delays and the scheduled elapsed time in minutes:
    sched_dep_utc  = FlightDate + CRSDepTime at the origin airport, converted to UTC
    actual_dep_utc = sched_dep_utc + DepDelay
    sched_arr_utc  = sched_dep_utc + CRSElapsedTime
    actual_arr_utc = sched_arr_utc + ArrDelay          (empty when cancelled or diverted)
This avoids guessing "next day" for flights that cross midnight or time zones.
"""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from etl.config import CLEAN_CONTAINER, RAW_CONTAINER, TOP30_AIRPORTS
from etl.storage import LakeSink, Sink, to_parquet_bytes

SOURCE = "bts"

URL_TEMPLATE = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)

# The 24 of BTS's 109 columns we use. Wheels times, diversion details etc. are dropped.
RAW_COLUMNS = [
    "FlightDate",
    "Reporting_Airline",
    "DOT_ID_Reporting_Airline",
    "Tail_Number",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "OriginState",
    "Dest",
    "DestState",
    "CRSDepTime",
    "DepDelay",
    "TaxiOut",
    "TaxiIn",
    "CRSElapsedTime",
    "ArrDelay",
    "Cancelled",
    "CancellationCode",
    "Diverted",
    "Distance",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
]

REQUIRED_COLUMNS = [
    "FlightDate",
    "Reporting_Airline",
    "DOT_ID_Reporting_Airline",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "CRSElapsedTime",
    "Cancelled",
    "Diverted",
]

# Numeric columns that may be empty (e.g. no DepDelay for a cancelled flight).
OPTIONAL_NUMERIC = [
    "DepDelay",
    "TaxiOut",
    "TaxiIn",
    "ArrDelay",
    "Distance",
    "CarrierDelay",
    "WeatherDelay",
    "NASDelay",
    "SecurityDelay",
    "LateAircraftDelay",
]

DELAY_CAUSES = {
    "CarrierDelay": "carrier_delay_min",
    "WeatherDelay": "weather_delay_min",
    "NASDelay": "nas_delay_min",
    "SecurityDelay": "security_delay_min",
    "LateAircraftDelay": "late_aircraft_delay_min",
}

# Same columns, same order as dbo.stg_flights.
STG_COLUMNS = [
    "month_key",
    "date_key",
    "carrier_code",
    "dot_airline_id",
    "flight_number",
    "tail_number",
    "origin",
    "origin_state",
    "dest",
    "dest_state",
    "distance_mi",
    "sched_dep_local",
    "dep_local_hour",
    "sched_dep_utc",
    "actual_dep_utc",
    "sched_arr_utc",
    "actual_arr_utc",
    "crs_elapsed_min",
    "dep_delay_min",
    "arr_delay_min",
    "taxi_out_min",
    "taxi_in_min",
    "is_cancelled",
    "cancellation_code",
    "is_diverted",
    *DELAY_CAUSES.values(),
]

# Matches the unique key of dbo.fact_flights.
NATURAL_KEY = ["date_key", "carrier_code", "flight_number", "origin", "dest", "sched_dep_local"]


def raw_path(month_key: int) -> str:
    return f"{SOURCE}/{month_key}/on_time_{month_key}.zip"


def clean_path(month_key: int, table: str) -> str:
    return f"{SOURCE}/{month_key}/{table}.parquet"


@dataclass
class TransformResult:
    clean: pd.DataFrame
    rejected: pd.DataFrame
    stats: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------- download / read
def download(month_key: int, *, retries: int = 3, timeout: int = 300, verify: bool = True) -> bytes:
    """Download one month's zip from BTS. The BTS server sometimes cuts downloads, so retry."""
    import requests

    year, month = divmod(month_key, 100)
    url = URL_TEMPLATE.format(year=year, month=month)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout, verify=verify)
            response.raise_for_status()
            _check_zip(response.content)
            return response.content
        except (requests.RequestException, zipfile.BadZipFile, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(10 * attempt)
    raise RuntimeError(f"BTS download failed for {month_key} after {retries} tries: {last_error}")


def _check_zip(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise zipfile.BadZipFile("BTS zip is incomplete or corrupt")
        if not any(name.endswith(".csv") for name in archive.namelist()):
            raise ValueError("BTS zip contains no CSV file")


def read_raw(raw: bytes) -> pd.DataFrame:
    """Read the CSV inside the zip as strings, keeping leading zeros ("0856") and empty values."""
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".csv"))
        with archive.open(name) as handle:
            # usecols also drops the empty 110th column created by each line's trailing comma.
            return pd.read_csv(handle, usecols=RAW_COLUMNS, dtype=str, keep_default_na=False)


@lru_cache(maxsize=1)
def load_airport_timezones() -> dict[str, str]:
    """IATA code → IANA time zone, e.g. 'LGA' → 'America/New_York'."""
    import airportsdata

    return {code: info["tz"] for code, info in airportsdata.load("IATA").items() if info.get("tz")}


# ---------------------------------------------------------------------------- validate
def validate(df: pd.DataFrame, month_key: int, airport_tz: Mapping[str, str]) -> pd.Series:
    """Return one reason per row ("" = valid). The first failing rule wins."""
    reasons = pd.Series("", index=df.index, dtype=object)

    def flag(mask: pd.Series, reason: str) -> None:
        reasons.loc[mask & (reasons == "")] = reason

    for column in REQUIRED_COLUMNS:
        flag(df[column] == "", f"missing {column}")

    flight_date = pd.to_datetime(df["FlightDate"], format="%Y-%m-%d", errors="coerce")
    flag(flight_date.isna(), "bad FlightDate")
    flag(
        flight_date.notna() & (flight_date.dt.year * 100 + flight_date.dt.month != month_key),
        "FlightDate outside month",
    )

    hhmm = df["CRSDepTime"]
    well_formed = hhmm.str.fullmatch(r"\d{4}").fillna(False).astype(bool)
    hours = pd.to_numeric(hhmm.str[:2], errors="coerce")
    minutes = pd.to_numeric(hhmm.str[2:], errors="coerce")
    valid_time = well_formed & (((hours < 24) & (minutes < 60)) | (hhmm == "2400"))
    flag(~valid_time, "bad CRSDepTime")

    for column in ["DOT_ID_Reporting_Airline", "CRSElapsedTime", "Cancelled", "Diverted"]:
        flag(pd.to_numeric(df[column], errors="coerce").isna(), f"non-numeric {column}")
    for column in OPTIONAL_NUMERIC:
        not_empty = df[column] != ""
        flag(not_empty & pd.to_numeric(df[column], errors="coerce").isna(), f"non-numeric {column}")

    cancelled = pd.to_numeric(df["Cancelled"], errors="coerce")
    diverted = pd.to_numeric(df["Diverted"], errors="coerce")
    flag(~cancelled.isin([0, 1]), "Cancelled not 0/1")
    flag(~diverted.isin([0, 1]), "Diverted not 0/1")
    bad_code = ~df["CancellationCode"].isin(["A", "B", "C", "D"])
    flag((cancelled == 1) & bad_code, "bad CancellationCode")

    flag(df["Origin"].map(airport_tz).isna(), "unknown origin time zone")
    return reasons


# ---------------------------------------------------------------------------- transform
def _minutes(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").round().astype("Int64")


def _as_timedelta(minutes: pd.Series) -> pd.Series:
    """Nullable minutes → timedelta (missing → NaT)."""
    return pd.to_timedelta(minutes.astype("float64"), unit="m")


def _to_utc(local: pd.Series, zones: pd.Series) -> pd.Series:
    """Naive local datetimes + IANA zone per row → naive UTC datetimes.

    Ambiguous times (the repeated hour in November) are read as standard time; times that don't
    exist (the skipped hour in March) are moved forward. Scheduled departures rarely fall there.
    """
    parts = []
    for zone, index in zones.groupby(zones).groups.items():
        chunk = local.loc[index]
        aware = chunk.dt.tz_localize(
            zone, ambiguous=np.zeros(len(chunk), dtype=bool), nonexistent="shift_forward"
        )
        parts.append(aware.dt.tz_convert("UTC").dt.tz_localize(None))
    if not parts:
        return pd.Series(pd.NaT, index=local.index, dtype="datetime64[ns]")
    return pd.concat(parts).reindex(local.index)


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


def _build_clean(df: pd.DataFrame, month_key: int, airport_tz: Mapping[str, str]) -> pd.DataFrame:
    flight_date = pd.to_datetime(df["FlightDate"], format="%Y-%m-%d")
    hours = df["CRSDepTime"].str[:2].astype(int)
    minutes = df["CRSDepTime"].str[2:].astype(int)
    # "2400" becomes 00:00 the next day because hours are added, not set.
    sched_dep_local = flight_date + pd.to_timedelta(hours * 60 + minutes, unit="m")

    sched_dep_utc = _to_utc(sched_dep_local, df["Origin"].map(airport_tz))
    crs_elapsed = _minutes(df["CRSElapsedTime"])
    dep_delay = _minutes(df["DepDelay"])
    arr_delay = _minutes(df["ArrDelay"])
    sched_arr_utc = sched_dep_utc + _as_timedelta(crs_elapsed)
    actual_dep_utc = sched_dep_utc + _as_timedelta(dep_delay)
    actual_arr_utc = sched_arr_utc + _as_timedelta(arr_delay)

    def empty_to_none(series: pd.Series) -> pd.Series:
        return series.where(series != "", None)

    clean = pd.DataFrame(
        {
            "month_key": month_key,
            "date_key": (flight_date.dt.strftime("%Y%m%d")).astype(int),
            "carrier_code": df["Reporting_Airline"],
            "dot_airline_id": _minutes(df["DOT_ID_Reporting_Airline"]),
            "flight_number": df["Flight_Number_Reporting_Airline"],
            "tail_number": empty_to_none(df["Tail_Number"]),
            "origin": df["Origin"],
            "origin_state": empty_to_none(df["OriginState"]),
            "dest": df["Dest"],
            "dest_state": empty_to_none(df["DestState"]),
            "distance_mi": _minutes(df["Distance"]),
            "sched_dep_local": sched_dep_local,
            "dep_local_hour": (hours % 24).astype("int16"),
            "sched_dep_utc": sched_dep_utc,
            "actual_dep_utc": actual_dep_utc,
            "sched_arr_utc": sched_arr_utc,
            "actual_arr_utc": actual_arr_utc,
            "crs_elapsed_min": crs_elapsed,
            "dep_delay_min": dep_delay,
            "arr_delay_min": arr_delay,
            "taxi_out_min": _minutes(df["TaxiOut"]),
            "taxi_in_min": _minutes(df["TaxiIn"]),
            "is_cancelled": pd.to_numeric(df["Cancelled"]) == 1,
            "cancellation_code": empty_to_none(df["CancellationCode"]),
            "is_diverted": pd.to_numeric(df["Diverted"]) == 1,
            **{target: _minutes(df[source]) for source, target in DELAY_CAUSES.items()},
        },
        index=df.index,
    )
    return clean[STG_COLUMNS]


def transform(
    raw: pd.DataFrame, month_key: int, airport_tz: Mapping[str, str] | None = None
) -> TransformResult:
    """Scope, validate and clean one month. Pure: no network, no Azure."""
    tz = airport_tz if airport_tz is not None else load_airport_timezones()
    df = raw[RAW_COLUMNS].apply(lambda column: column.astype(str).str.strip())

    in_scope = df["Origin"].isin(TOP30_AIRPORTS) & df["Dest"].isin(TOP30_AIRPORTS)
    df = df[in_scope]

    reasons = validate(df, month_key, tz)
    valid = reasons == ""
    clean = _build_clean(df[valid], month_key, tz)

    duplicate = clean.duplicated(NATURAL_KEY, keep="first")
    duplicate_index = clean.index[duplicate]
    reasons.loc[duplicate_index] = "duplicate natural key"
    clean = clean[~duplicate].reset_index(drop=True)

    bad = reasons != ""
    rejected = _rejected_rows(df[bad], reasons[bad], month_key)

    stats = {
        "rows_read": int(len(raw)),
        "rows_out_of_scope": int((~in_scope).sum()),
        "rows_clean": int(len(clean)),
        "rows_rejected": int(len(rejected)),
    }
    return TransformResult(clean=clean, rejected=rejected, stats=stats)


# ---------------------------------------------------------------------------- run
def ingest_month(month_key: int, sink: Sink | None = None, raw: bytes | None = None) -> dict:
    """Download (unless raw is given), keep the raw zip, write clean + rejected parquet files.

    Re-running a month overwrites its files, so it never creates duplicates.
    """
    sink = sink if sink is not None else LakeSink()
    if raw is None:
        verify = os.getenv("BTS_VERIFY_SSL", "true").lower() != "false"
        raw = download(month_key, verify=verify)

    raw_location = sink.write_bytes(RAW_CONTAINER, raw_path(month_key), raw)
    result = transform(read_raw(raw), month_key)
    clean_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "flights"), to_parquet_bytes(result.clean)
    )
    rejected_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "rejected"), to_parquet_bytes(result.rejected)
    )
    return {
        "source": SOURCE,
        "month_key": month_key,
        **result.stats,
        "raw_file": raw_location,
        "clean_file": clean_location,
        "rejected_file": rejected_location,
    }
