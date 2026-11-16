"""Unit tests for the BTS template. No network, no Azure: transform() is pure pandas.

Rows are built in the exact string format of the real BTS CSV ("0856", "-5.00", "1.00", "").
"""

import io
import zipfile

import pandas as pd

from etl import bts

# Test time zones (real ones come from airportsdata). SEA is deliberately missing.
TZ = {
    "LGA": "America/New_York",
    "ORD": "America/Chicago",
    "LAX": "America/Los_Angeles",
    "OMA": "America/Chicago",
}


def row(**overrides: str) -> dict[str, str]:
    """One on-time LGA → ORD flight on 2024-01-08; override any field."""
    base = {column: "" for column in bts.RAW_COLUMNS}
    base.update(
        FlightDate="2024-01-08",
        Reporting_Airline="9E",
        DOT_ID_Reporting_Airline="20363",
        Tail_Number="N485PX",
        Flight_Number_Reporting_Airline="4801",
        Origin="LGA",
        OriginState="NY",
        Dest="ORD",
        DestState="IL",
        CRSDepTime="0856",
        DepDelay="-5.00",
        TaxiOut="25.00",
        TaxiIn="4.00",
        CRSElapsedTime="150.00",
        ArrDelay="-11.00",
        Cancelled="0.00",
        Diverted="0.00",
        Distance="733.00",
    )
    base.update(overrides)
    return base


def run(*rows: dict[str, str], month_key: int = 202401) -> bts.TransformResult:
    return bts.transform(pd.DataFrame(list(rows)), month_key, airport_tz=TZ)


def test_on_time_flight_times_are_converted_to_utc():
    result = run(row())
    flight = result.clean.iloc[0]
    # 08:56 EST (UTC-5) → 13:56 UTC; left 5 min early; arrival = +150 min; landed 11 min early
    assert flight["sched_dep_local"] == pd.Timestamp("2024-01-08 08:56")
    assert flight["sched_dep_utc"] == pd.Timestamp("2024-01-08 13:56")
    assert flight["actual_dep_utc"] == pd.Timestamp("2024-01-08 13:51")
    assert flight["sched_arr_utc"] == pd.Timestamp("2024-01-08 16:26")
    assert flight["actual_arr_utc"] == pd.Timestamp("2024-01-08 16:15")
    assert flight["dep_local_hour"] == 8
    assert flight["date_key"] == 20240108
    assert flight["dep_delay_min"] == -5
    assert not flight["is_cancelled"]
    assert result.stats == {
        "rows_read": 1,
        "rows_out_of_scope": 0,
        "rows_clean": 1,
        "rows_rejected": 0,
    }


def test_2400_departure_is_midnight_next_day():
    flight = run(row(CRSDepTime="2400")).clean.iloc[0]
    assert flight["sched_dep_local"] == pd.Timestamp("2024-01-09 00:00")
    assert flight["dep_local_hour"] == 0
    assert flight["date_key"] == 20240108  # BTS flight date is kept


def test_summer_time_uses_daylight_offset():
    flight = run(row(FlightDate="2024-07-15", Origin="LAX", CRSDepTime="1000"), month_key=202407)
    # 10:00 PDT (UTC-7) → 17:00 UTC
    assert flight.clean.iloc[0]["sched_dep_utc"] == pd.Timestamp("2024-07-15 17:00")


def test_cancelled_flight_has_no_actual_times():
    flight = run(
        row(Cancelled="1.00", CancellationCode="B", DepDelay="", ArrDelay="", TaxiOut="", TaxiIn="")
    ).clean.iloc[0]
    assert flight["is_cancelled"]
    assert flight["cancellation_code"] == "B"
    assert pd.isna(flight["actual_dep_utc"])
    assert pd.isna(flight["actual_arr_utc"])
    assert pd.isna(flight["dep_delay_min"])


def test_diverted_flight_has_no_actual_arrival():
    flight = run(row(Diverted="1.00", ArrDelay="")).clean.iloc[0]
    assert flight["is_diverted"]
    assert pd.notna(flight["actual_dep_utc"])
    assert pd.isna(flight["actual_arr_utc"])


def test_delay_causes_are_parsed():
    flight = run(
        row(
            ArrDelay="45.00",
            CarrierDelay="10.00",
            WeatherDelay="30.00",
            NASDelay="5.00",
            SecurityDelay="0.00",
            LateAircraftDelay="0.00",
        )
    ).clean.iloc[0]
    assert flight["weather_delay_min"] == 30
    assert flight["carrier_delay_min"] == 10


def test_flights_outside_top30_are_dropped_not_rejected():
    result = run(row(), row(Dest="OMA"))
    assert result.stats["rows_out_of_scope"] == 1
    assert len(result.clean) == 1
    assert len(result.rejected) == 0


def test_invalid_rows_are_rejected_with_a_reason():
    result = run(
        row(CRSDepTime="2561"),
        row(Flight_Number_Reporting_Airline="", CRSDepTime="0900"),
        row(Origin="SEA", CRSDepTime="1000"),  # SEA has no time zone in TZ
        row(Cancelled="1.00", CancellationCode="", CRSDepTime="1100"),
        row(FlightDate="2024-02-01", CRSDepTime="1200"),
        row(DepDelay="abc", CRSDepTime="1300"),
    )
    assert len(result.clean) == 0
    assert sorted(result.rejected["reason"]) == sorted(
        [
            "bad CRSDepTime",
            "missing Flight_Number_Reporting_Airline",
            "unknown origin time zone",
            "bad CancellationCode",
            "FlightDate outside month",
            "non-numeric DepDelay",
        ]
    )
    assert set(result.rejected.columns) == {"source", "month_key", "reason", "raw_record"}
    assert '"CRSDepTime": "2561"' in result.rejected["raw_record"].iloc[0]


def test_duplicates_keep_the_first_row():
    result = run(row(Tail_Number="N1"), row(Tail_Number="N2"))
    assert len(result.clean) == 1
    assert result.clean.iloc[0]["tail_number"] == "N1"
    assert list(result.rejected["reason"]) == ["duplicate natural key"]


def test_clean_columns_match_staging_table():
    assert list(run(row()).clean.columns) == bts.STG_COLUMNS


def test_read_raw_handles_real_file_layout():
    # Real files have 109 columns plus a trailing comma on every line.
    header = ",".join(f'"{c}"' for c in ["Year", *bts.RAW_COLUMNS]) + ","
    values = ",".join(["2024", *(f'"{row()[c]}"' for c in bts.RAW_COLUMNS)]) + ","
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("On_Time_2024_1.csv", f"{header}\n{values}\n")

    raw = bts.read_raw(buffer.getvalue())
    assert list(raw.columns) == bts.RAW_COLUMNS
    assert raw.loc[0, "CRSDepTime"] == "0856"  # leading zero kept
    assert raw.loc[0, "CarrierDelay"] == ""  # empty stays empty, not NaN
