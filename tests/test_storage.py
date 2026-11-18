"""Parquet written by the ETL must be readable by Azure Data Factory."""

import io

import pandas as pd
import pyarrow.parquet as pq

from etl.storage import to_parquet_bytes


def test_timestamps_are_written_in_milliseconds():
    # ADF reads nanosecond timestamps as Int64 and fails to load them into DATETIME2.
    df = pd.DataFrame({"sched_dep_utc": pd.to_datetime(["2024-01-08 13:56"])})
    table = pq.read_table(io.BytesIO(to_parquet_bytes(df)))
    assert str(table.schema.field("sched_dep_utc").type) == "timestamp[ms]"