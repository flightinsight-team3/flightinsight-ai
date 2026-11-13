"""BTS On-Time Performance.

ingest_month: download the month zip -> raw/bts/<month>/ ; clean, convert to UTC, validate
              -> clean/bts/<month>/flights.parquet ; rejected rows -> stg_rejected
load_month:   delete-and-reload the month in the SQL staging table from the clean parquet
"""


def raw_path(month_key: int) -> str:
    return f"bts/{month_key}/on_time_{month_key}.zip"


def clean_path(month_key: int) -> str:
    return f"bts/{month_key}/flights.parquet"


def ingest_month(month_key: int) -> dict:
    raise NotImplementedError("bts.ingest_month")


def load_month(month_key: int) -> dict:
    raise NotImplementedError("bts.load_month")
