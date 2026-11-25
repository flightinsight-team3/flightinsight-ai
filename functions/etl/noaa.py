"""DS02 · NOAA Local Climatological Data (hourly + daily), one month at a time.

Follows the same template as BTS (see docs/etl-template.md):

    download(month_key)            dict[station_id -> yearly CSV bytes]           (network)
    read_raw(raws)                 DataFrame of strings, nothing interpreted       (pure)
    validate(df, month_key)        one rejection reason per row, "" = valid        (pure)
    transform(raws, month_key)     clean hourly + daily + stations + rejected      (pure)
    ingest_month(month_key, sink)  runs the steps, writes raw/ and clean/ files    (Azure or local)

LCD data is per station, per year: one file holds the whole year's observations. For a month_key
such as 202401 we download the 2024 CSV for each top30 station, keep only rows whose local date
falls in that month, split into hourly / daily rows, and write parquet.

Times. LCD reports every DATE in LST (Local Standard Time, no DST). To convert to UTC we add the
station's fixed standard offset (e.g. EST = +5h, PST = +8h). This is why NOAA_STATIONS carries
`std_offset_hours` per station, not an IANA zone: IANA would apply DST.

Output in the Data Lake, container `clean`, folder noaa/<yyyymm>/:
    hourly.parquet      one row per station-hour; columns match dbo.stg_weather_hourly
    daily.parquet       one row per station-day;  columns match dbo.stg_weather_daily
    stations.parquet    one row per station;      columns match dbo.stg_weather_stations
    rejected.parquet    rows that failed validation; columns match dbo.stg_rejected
"""

from __future__ import annotations

import io
import json
import os
import re
import time
from dataclasses import dataclass, field

import pandas as pd

from etl.config import CLEAN_CONTAINER, RAW_CONTAINER
from etl.storage import LakeSink, Sink, to_parquet_bytes

SOURCE = "noaa"
URL_TEMPLATE = (
    "https://www.ncei.noaa.gov/data/local-climatological-data/access/{year}/{station_id}.csv"
)

# The 30 top US airports and their NOAA LCD stations. Each tuple is
# (iata, station_id, icao, station_name, latitude, longitude, std_offset_hours).
# std_offset is the *standard* UTC offset (no DST) because LCD reports LST, not local time.
# station_id = USAF+WBAN as used in NCEI LCD URLs (checked against isd-history.csv).
_STATIONS_RAW: tuple[tuple[str, str, str, str, float, float, int], ...] = (
    ("ATL", "72219013874", "KATL", "ATLANTA HARTSFIELD INTL AP",            33.6301, -84.4419, -5),
    ("AUS", "72254013904", "KAUS", "AUSTIN BERGSTROM INTL AP",              30.1831, -97.6799, -6),
    ("BNA", "72327013897", "KBNA", "NASHVILLE INTL AP",                     36.1245, -86.6782, -6),
    ("BOS", "72509014739", "KBOS", "BOSTON LOGAN INTL AP",                  42.3606, -71.0106, -5),
    ("BWI", "72406093721", "KBWI", "BALTIMORE WASHINGTON INTL AP",          39.1733, -76.6839, -5),
    ("CLT", "72314013881", "KCLT", "CHARLOTTE DOUGLAS AP",                  35.2139, -80.9431, -5),
    ("DCA", "72405013743", "KDCA", "WASHINGTON REAGAN NATIONAL AP",         38.8521, -77.0376, -5),
    ("DEN", "72565003017", "KDEN", "DENVER INTL AP",                        39.8328, -104.6575, -7),
    ("DFW", "72259003927", "KDFW", "DALLAS FORT WORTH INTL AP",             32.8968, -97.0380, -6),
    ("DTW", "72537094847", "KDTW", "DETROIT METRO WAYNE CO AP",             42.2124, -83.3534, -5),
    ("EWR", "72502014734", "KEWR", "NEWARK LIBERTY INTL AP",                40.6895, -74.1745, -5),
    ("FLL", "74783012849", "KFLL", "FORT LAUDERDALE HOLLYWOOD INTL AP",     26.0725, -80.1528, -5),
    ("IAD", "72403093738", "KIAD", "WASHINGTON DULLES INTL AP",             38.9445, -77.4558, -5),
    ("IAH", "72243012960", "KIAH", "HOUSTON INTERCONTINENTAL AP",           29.9902, -95.3368, -6),
    ("JFK", "74486094789", "KJFK", "NEW YORK J F KENNEDY INTL AP",          40.6397, -73.7789, -5),
    ("LAS", "72386023169", "KLAS", "LAS VEGAS MCCARRAN INTL AP",            36.0840, -115.1537, -8),
    ("LAX", "72295023174", "KLAX", "LOS ANGELES INTL AP",                   33.9381, -118.3889, -8),
    ("LGA", "72503014732", "KLGA", "NEW YORK LA GUARDIA AP",                40.7792, -73.8800, -5),
    ("MCO", "72205012815", "KMCO", "ORLANDO INTL AP",                       28.4312, -81.3081, -5),
    ("MDW", "72534014819", "KMDW", "CHICAGO MIDWAY AP",                     41.7868, -87.7522, -6),
    ("MIA", "72202012839", "KMIA", "MIAMI INTL AP",                         25.7919, -80.3158, -5),
    ("MSP", "72658014922", "KMSP", "MINNEAPOLIS ST PAUL INTL AP",           44.8830, -93.2223, -6),
    ("ORD", "72530094846", "KORD", "CHICAGO OHARE INTL AP",                 41.9950, -87.9336, -6),
    ("PHL", "72408013739", "KPHL", "PHILADELPHIA INTL AP",                  39.8721, -75.2411, -5),
    ("PHX", "72278023183", "KPHX", "PHOENIX SKY HARBOR INTL AP",            33.4342, -112.0117, -7),
    ("SAN", "72290023188", "KSAN", "SAN DIEGO INTL AP",                     32.7336, -117.1831, -8),
    ("SEA", "72793024233", "KSEA", "SEATTLE TACOMA INTL AP",                47.4447, -122.3139, -8),
    ("SFO", "72494023234", "KSFO", "SAN FRANCISCO INTL AP",                 37.6197, -122.3656, -8),
    ("SLC", "72572024127", "KSLC", "SALT LAKE CITY INTL AP",                40.7884, -111.9778, -7),
    ("TPA", "72211012842", "KTPA", "TAMPA INTL AP",                         27.9755, -82.5332, -5),
)  # fmt: skip

NOAA_STATIONS: tuple[dict, ...] = tuple(
    {
        "iata": iata, "station_id": sid, "icao": icao, "name": name,
        "latitude": lat, "longitude": lon, "std_offset_hours": off,
    }
    for iata, sid, icao, name, lat, lon, off in _STATIONS_RAW
)  # fmt: skip

STATION_BY_ID: dict[str, dict] = {s["station_id"]: s for s in NOAA_STATIONS}

# LCD columns we read (as strings). Everything else is dropped.
RAW_COLUMNS = [
    "STATION",
    "DATE",
    "REPORT_TYPE",
    "HourlyDryBulbTemperature",
    "HourlyPrecipitation",
    "HourlyWindSpeed",
    "HourlyWindGustSpeed",
    "HourlyVisibility",
    "HourlyPresentWeatherType",
    "DailySnowfall",
    "DailySnowDepth",
    "DailyPrecipitation",
]

HOURLY_REPORT_TYPES = frozenset({"FM-15", "FM-12", "FM-16"})  # scheduled/special METARs
DAILY_REPORT_TYPE = "SOD"  # Summary Of the Day

# LCD measurement codes we need to strip before numeric conversion:
#   "45s"  -> suspect; keep 45
#   "10.00V" -> variable; keep 10
#   "0.00s" -> keep 0.00
_NUMERIC_SUFFIX = re.compile(r"[a-zA-Z*]+$")
# Present-weather codes that make a flight day "adverse" (METAR vocabulary).
_ADVERSE_CODES = ("TS", "FZ", "SN", "GR", "GS", "FG", "BR", "SQ", "SS", "DS", "VA")

STG_HOURLY_COLUMNS = [
    "month_key",
    "station_id",
    "obs_hour_utc",
    "local_date_key",
    "temperature_f",
    "precipitation_in",
    "is_trace_precip",
    "wind_speed_mph",
    "wind_gust_mph",
    "visibility_mi",
    "present_weather",
    "is_adverse",
]

STG_DAILY_COLUMNS = [
    "month_key",
    "station_id",
    "date_key",
    "snowfall_in",
    "snow_depth_in",
    "precipitation_in",
]

STG_STATION_COLUMNS = [
    "snapshot_key",
    "station_id",
    "icao_code",
    "station_name",
    "latitude",
    "longitude",
]


def raw_path(month_key: int, station_id: str) -> str:
    return f"{SOURCE}/{month_key}/{station_id}.csv"


def clean_path(month_key: int, table: str) -> str:
    return f"{SOURCE}/{month_key}/{table}.parquet"


@dataclass
class TransformResult:
    hourly: pd.DataFrame
    daily: pd.DataFrame
    stations: pd.DataFrame
    rejected: pd.DataFrame
    stats: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------- download / read
def download(
    month_key: int,
    stations: tuple[dict, ...] = NOAA_STATIONS,
    *,
    retries: int = 3,
    timeout: int = 180,
    verify: bool = True,
) -> dict[str, bytes]:
    """Download the yearly LCD CSV for every station in `stations`. Returns {station_id: bytes}."""
    import requests

    year = month_key // 100
    out: dict[str, bytes] = {}
    for station in stations:
        sid = station["station_id"]
        url = URL_TEMPLATE.format(year=year, station_id=sid)
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = requests.get(url, timeout=timeout, verify=verify)
                response.raise_for_status()
                if b"STATION" not in response.content[:200]:
                    raise ValueError(f"{sid}: response missing LCD header")
                out[sid] = response.content
                break
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(5 * attempt)
        else:
            raise RuntimeError(f"NOAA download failed for {sid} ({year}): {last_error}")
    return out


def read_raw(raws: dict[str, bytes]) -> pd.DataFrame:
    """Concatenate every station CSV into one string DataFrame with only RAW_COLUMNS."""
    frames: list[pd.DataFrame] = []
    for sid, data in raws.items():
        df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
        missing = [c for c in RAW_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{sid}: LCD CSV missing columns {missing}")
        frames.append(df[RAW_COLUMNS])
    if not frames:
        return pd.DataFrame(columns=RAW_COLUMNS)
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------- validate
def validate(df: pd.DataFrame, month_key: int) -> pd.Series:
    """Return one reason per row ("" = valid). First failing rule wins."""
    reasons = pd.Series("", index=df.index, dtype=object)

    def flag(mask: pd.Series, reason: str) -> None:
        reasons.loc[mask & (reasons == "")] = reason

    flag(df["STATION"] == "", "missing STATION")
    flag(~df["STATION"].isin(STATION_BY_ID), "unknown STATION")

    flag(pd.to_datetime(df["DATE"], errors="coerce").isna(), "bad DATE")
    return reasons


# ---------------------------------------------------------------------------- transform
def _to_numeric(series: pd.Series) -> pd.Series:
    """LCD numeric fields can have trailing flag letters; strip and coerce."""
    stripped = series.astype(str).str.replace(_NUMERIC_SUFFIX, "", regex=True)
    return pd.to_numeric(stripped, errors="coerce")


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


def _utc_from_lst(local_times: pd.Series, offsets_hours: pd.Series) -> pd.Series:
    """LST wall-clock + fixed standard offset -> naive UTC."""
    return local_times - pd.to_timedelta(offsets_hours.astype("float64"), unit="h")


def _is_adverse(present_weather: pd.Series, visibility_mi: pd.Series) -> pd.Series:
    text = present_weather.fillna("").astype(str).str.upper()
    code_hit = pd.Series(False, index=text.index)
    for code in _ADVERSE_CODES:
        code_hit = code_hit | text.str.contains(code, regex=False, na=False)
    low_vis = visibility_mi.fillna(999).lt(1.0)
    return (code_hit | low_vis).astype("bool")


def _build_hourly(df: pd.DataFrame, month_key: int) -> pd.DataFrame:
    station_meta = df["STATION"].map(STATION_BY_ID)
    offsets = station_meta.map(lambda s: s["std_offset_hours"])
    local_dt = pd.to_datetime(df["DATE"])
    utc_dt = _utc_from_lst(local_dt, offsets)
    obs_hour_utc = utc_dt.dt.floor("h")

    temperature = _to_numeric(df["HourlyDryBulbTemperature"]).round(1)

    precip_raw = df["HourlyPrecipitation"].astype(str).str.strip()
    is_trace = precip_raw.str.upper() == "T"
    precip = _to_numeric(precip_raw.where(~is_trace, "0")).round(2)

    wind_speed = _to_numeric(df["HourlyWindSpeed"]).round().astype("Int64")
    wind_gust = _to_numeric(df["HourlyWindGustSpeed"]).round().astype("Int64")
    visibility = _to_numeric(df["HourlyVisibility"]).round(2)
    present_weather = (
        df["HourlyPresentWeatherType"]
        .astype(str)
        .str.strip()
        .where(df["HourlyPresentWeatherType"].astype(str).str.strip() != "", None)
    )

    clean = pd.DataFrame(
        {
            "month_key": month_key,
            "station_id": df["STATION"],
            "obs_hour_utc": obs_hour_utc,
            "local_date_key": (local_dt.dt.strftime("%Y%m%d")).astype(int),
            "temperature_f": temperature,
            "precipitation_in": precip,
            "is_trace_precip": is_trace.astype("bool"),
            "wind_speed_mph": wind_speed,
            "wind_gust_mph": wind_gust,
            "visibility_mi": visibility,
            "present_weather": present_weather,
            "is_adverse": _is_adverse(present_weather, visibility),
        },
        index=df.index,
    )
    return clean[STG_HOURLY_COLUMNS]


def _build_daily(df: pd.DataFrame, month_key: int) -> pd.DataFrame:
    local_dt = pd.to_datetime(df["DATE"])
    clean = pd.DataFrame(
        {
            "month_key": month_key,
            "station_id": df["STATION"],
            "date_key": (local_dt.dt.strftime("%Y%m%d")).astype(int),
            "snowfall_in": _to_numeric(df["DailySnowfall"]).round(1),
            "snow_depth_in": _to_numeric(df["DailySnowDepth"]).round(1),
            "precipitation_in": _to_numeric(df["DailyPrecipitation"]).round(2),
        },
        index=df.index,
    )
    return clean[STG_DAILY_COLUMNS]


def _build_stations(month_key: int) -> pd.DataFrame:
    rows = [
        {
            "snapshot_key": month_key,
            "station_id": s["station_id"],
            "icao_code": s["icao"],
            "station_name": s["name"],
            "latitude": s["latitude"],
            "longitude": s["longitude"],
        }
        for s in NOAA_STATIONS
    ]
    return pd.DataFrame(rows, columns=STG_STATION_COLUMNS)


def transform(raws: dict[str, bytes] | pd.DataFrame, month_key: int) -> TransformResult:
    """Scope, validate and split one month of LCD data into hourly + daily. Pure."""
    df = raws if isinstance(raws, pd.DataFrame) else read_raw(raws)
    df = df[RAW_COLUMNS].apply(lambda column: column.astype(str).str.strip())
    rows_read = len(df)

    # Each LCD file holds a whole year plus monthly summaries; other months and other report
    # types are out of scope (counted, not rejected).
    parsed = pd.to_datetime(df["DATE"], errors="coerce")
    row_type = df["REPORT_TYPE"]
    supported = row_type.isin(HOURLY_REPORT_TYPES) | (row_type == DAILY_REPORT_TYPE)
    in_month = parsed.dt.year * 100 + parsed.dt.month == month_key
    out_of_scope = parsed.notna() & ~(supported & in_month)
    df = df[~out_of_scope]
    row_type = row_type[~out_of_scope]

    reasons = validate(df, month_key)
    valid = reasons == ""

    hourly_rows = df[valid & row_type.isin(HOURLY_REPORT_TYPES)]
    daily_rows = df[valid & (row_type == DAILY_REPORT_TYPE)]

    hourly = _build_hourly(hourly_rows, month_key)
    # Stations report several times an hour (routine + special METARs); keep the first.
    extra_obs = hourly.duplicated(["station_id", "obs_hour_utc"], keep="first")
    hourly = hourly[~extra_obs].reset_index(drop=True)

    daily = _build_daily(daily_rows, month_key)
    duplicate_d = daily.duplicated(["station_id", "date_key"], keep="first")
    reasons.loc[daily.index[duplicate_d]] = "duplicate station-date"
    daily = daily[~duplicate_d].reset_index(drop=True)

    bad = reasons != ""
    rejected = _rejected_rows(df[bad], reasons[bad], month_key)
    stations = _build_stations(month_key)

    stats = {
        "rows_read": int(rows_read),
        "rows_out_of_scope": int(out_of_scope.sum()),
        "rows_extra_obs": int(extra_obs.sum()),
        "rows_hourly": int(len(hourly)),
        "rows_daily": int(len(daily)),
        "rows_rejected": int(len(rejected)),
        "rows_stations": int(len(stations)),
    }
    return TransformResult(
        hourly=hourly, daily=daily, stations=stations, rejected=rejected, stats=stats
    )


# ---------------------------------------------------------------------------- run
def ingest_month(
    month_key: int,
    sink: Sink | None = None,
    raw: dict[str, bytes] | None = None,
) -> dict:
    """Download (unless raw is given), keep raw CSVs, write hourly/daily/stations/rejected parquet.

    Re-running a month overwrites its files, so it never creates duplicates.
    """
    sink = sink if sink is not None else LakeSink()
    if raw is None:
        verify = os.getenv("NOAA_VERIFY_SSL", "true").lower() != "false"
        raw = download(month_key, verify=verify)

    raw_locations: dict[str, str] = {}
    for sid, data in raw.items():
        raw_locations[sid] = sink.write_bytes(RAW_CONTAINER, raw_path(month_key, sid), data)

    result = transform(raw, month_key)
    hourly_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "hourly"), to_parquet_bytes(result.hourly)
    )
    daily_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "daily"), to_parquet_bytes(result.daily)
    )
    stations_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "stations"), to_parquet_bytes(result.stations)
    )
    rejected_location = sink.write_bytes(
        CLEAN_CONTAINER, clean_path(month_key, "rejected"), to_parquet_bytes(result.rejected)
    )
    return {
        "source": SOURCE,
        "month_key": month_key,
        **result.stats,
        "raw_files": raw_locations,
        "hourly_file": hourly_location,
        "daily_file": daily_location,
        "stations_file": stations_location,
        "rejected_file": rejected_location,
    }
