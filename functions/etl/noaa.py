"""NOAA Local Climatological Data (hourly + daily) for the stations in bridge_airport_station.

ingest_month: download LCD CSVs -> raw/noaa/<month>/ ; keep one observation per station-hour,
              convert local standard time to UTC -> clean/noaa/<month>/hourly.parquet, daily.parquet
load_month:   delete-and-reload the month in the SQL staging tables
"""


def clean_paths(month_key: int) -> dict[str, str]:
    return {
        "hourly": f"noaa/{month_key}/hourly.parquet",
        "daily": f"noaa/{month_key}/daily.parquet",
    }


def ingest_month(month_key: int) -> dict:
    raise NotImplementedError("noaa.ingest_month")


def load_month(month_key: int) -> dict:
    raise NotImplementedError("noaa.load_month")
