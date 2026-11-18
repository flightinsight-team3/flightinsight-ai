"""Unit tests for the DS02 NOAA template. No network, no Azure: transform() is pure pandas.

Rows are built in the exact string format of the real LCD CSV: empty values are "", numerics
can carry trailing flag letters ("45s", "10.00V"), trace precipitation is "T".
"""

import pandas as pd

from etl import noaa

# Reuse two real stations from the embedded top30 list so STATION_BY_ID resolves them.
LGA = next(s for s in noaa.NOAA_STATIONS if s["iata"] == "LGA")  # EST = UTC-5
LAX = next(s for s in noaa.NOAA_STATIONS if s["iata"] == "LAX")  # PST = UTC-8


def hourly_row(**overrides: str) -> dict[str, str]:
    """One normal FM-15 hourly observation at LGA, 2024-01-08 08:51 LST."""
    base = {column: "" for column in noaa.RAW_COLUMNS}
    base.update(
        STATION=LGA["station_id"],
        DATE="2024-01-08T08:51:00",
        REPORT_TYPE="FM-15",
        HourlyDryBulbTemperature="35",
        HourlyPrecipitation="0.00",
        HourlyWindSpeed="10",
        HourlyWindGustSpeed="",
        HourlyVisibility="10.00",
        HourlyPresentWeatherType="",
    )
    base.update(overrides)
    return base


def daily_row(**overrides: str) -> dict[str, str]:
    """One SOD row for LGA on 2024-01-08."""
    base = {column: "" for column in noaa.RAW_COLUMNS}
    base.update(
        STATION=LGA["station_id"],
        DATE="2024-01-08T23:59:00",
        REPORT_TYPE="SOD",
        DailySnowfall="0.5",
        DailySnowDepth="1.0",
        DailyPrecipitation="0.15",
    )
    base.update(overrides)
    return base


def run(*rows: dict[str, str], month_key: int = 202401) -> noaa.TransformResult:
    return noaa.transform(pd.DataFrame(list(rows)), month_key)


def test_hourly_row_is_converted_to_utc():
    result = run(hourly_row())
    row = result.hourly.iloc[0]
    # 08:51 EST (UTC-5, LST so no DST) -> 13:51 UTC, floored to 13:00
    assert row["obs_hour_utc"] == pd.Timestamp("2024-01-08 13:00")
    assert row["station_id"] == LGA["station_id"]
    assert row["local_date_key"] == 20240108
    assert row["temperature_f"] == 35.0
    assert row["precipitation_in"] == 0.0
    assert bool(row["is_trace_precip"]) is False
    assert row["wind_speed_mph"] == 10
    assert pd.isna(row["wind_gust_mph"])
    assert row["visibility_mi"] == 10.0
    assert bool(row["is_adverse"]) is False


def test_summer_hour_uses_standard_offset_not_dst():
    # LCD reports LST all year -> 10:00 "LST" at LAX in July is still PST (UTC-8), not PDT.
    result = run(
        hourly_row(STATION=LAX["station_id"], DATE="2024-07-15T10:00:00"),
        month_key=202407,
    )
    assert result.hourly.iloc[0]["obs_hour_utc"] == pd.Timestamp("2024-07-15 18:00")


def test_trace_precipitation_sets_flag():
    row = run(hourly_row(HourlyPrecipitation="T")).hourly.iloc[0]
    assert row["precipitation_in"] == 0.0
    assert bool(row["is_trace_precip"]) is True


def test_numeric_fields_strip_quality_suffixes():
    row = run(
        hourly_row(
            HourlyDryBulbTemperature="35s",
            HourlyWindSpeed="18s",
            HourlyVisibility="10.00V",
        )
    ).hourly.iloc[0]
    assert row["temperature_f"] == 35.0
    assert row["wind_speed_mph"] == 18
    assert row["visibility_mi"] == 10.0


def test_thunderstorm_marks_row_adverse():
    row = run(hourly_row(HourlyPresentWeatherType="TS:0 RA:02 |TS |")).hourly.iloc[0]
    assert bool(row["is_adverse"]) is True


def test_low_visibility_marks_row_adverse_even_without_weather_code():
    row = run(hourly_row(HourlyVisibility="0.50")).hourly.iloc[0]
    assert bool(row["is_adverse"]) is True


def test_daily_row_is_split_into_daily_table():
    result = run(daily_row())
    assert len(result.hourly) == 0
    assert len(result.daily) == 1
    row = result.daily.iloc[0]
    assert row["station_id"] == LGA["station_id"]
    assert row["date_key"] == 20240108
    assert row["snowfall_in"] == 0.5
    assert row["snow_depth_in"] == 1.0
    assert row["precipitation_in"] == 0.15


def test_invalid_rows_are_rejected_with_a_reason():
    result = run(
        hourly_row(STATION=""),                          # missing STATION
        hourly_row(STATION="99999999999"),               # unknown STATION
        hourly_row(DATE=""),                             # bad DATE
    )
    assert len(result.hourly) == 0
    assert sorted(result.rejected["reason"]) == sorted(
        ["missing STATION", "unknown STATION", "bad DATE"]
    )
    assert set(result.rejected.columns) == {"source", "month_key", "reason", "raw_record"}


def test_other_months_and_report_types_are_out_of_scope_not_rejected():
    result = run(
        hourly_row(),
        hourly_row(DATE="2024-02-01T08:00:00"),          # other month of the yearly file
        hourly_row(REPORT_TYPE="SOM"),                   # monthly summary
    )
    assert len(result.hourly) == 1
    assert len(result.rejected) == 0
    assert result.stats["rows_out_of_scope"] == 2


def test_extra_observations_in_the_same_hour_keep_the_first():
    result = run(
        hourly_row(DATE="2024-01-08T08:51:00", HourlyDryBulbTemperature="35"),
        hourly_row(DATE="2024-01-08T08:56:00", HourlyDryBulbTemperature="36", REPORT_TYPE="FM-16"),
    )
    assert len(result.hourly) == 1
    assert result.hourly.iloc[0]["temperature_f"] == 35.0
    assert len(result.rejected) == 0
    assert result.stats["rows_extra_obs"] == 1


def test_duplicate_station_date_keeps_the_first():
    result = run(
        daily_row(DailySnowfall="0.5"),
        daily_row(DailySnowfall="1.0"),
    )
    assert len(result.daily) == 1
    assert result.daily.iloc[0]["snowfall_in"] == 0.5
    assert list(result.rejected["reason"]) == ["duplicate station-date"]


def test_clean_columns_match_staging_tables():
    result = run(hourly_row(), daily_row())
    assert list(result.hourly.columns) == noaa.STG_HOURLY_COLUMNS
    assert list(result.daily.columns) == noaa.STG_DAILY_COLUMNS
    assert list(result.stations.columns) == noaa.STG_STATION_COLUMNS


def test_stations_snapshot_includes_all_top30():
    stations = run(hourly_row()).stations
    assert len(stations) == 30
    assert set(stations["station_id"]) == {s["station_id"] for s in noaa.NOAA_STATIONS}
    assert (stations["snapshot_key"] == 202401).all()


def test_read_raw_filters_and_concatenates_station_csvs():
    header = ",".join(["EXTRA1", *noaa.RAW_COLUMNS, "EXTRA2"]) + "\n"
    row_values = ",".join(["x", *(hourly_row()[c] for c in noaa.RAW_COLUMNS), "y"]) + "\n"
    raw_bytes = (header + row_values).encode("utf-8")
    df = noaa.read_raw({LGA["station_id"]: raw_bytes})
    assert list(df.columns) == noaa.RAW_COLUMNS
    assert df.loc[0, "STATION"] == LGA["station_id"]
    assert df.loc[0, "HourlyDryBulbTemperature"] == "35"
