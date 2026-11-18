"""Where ETL output is written: the Data Lake in Azure, or a local folder for development.

Every source writes through a Sink, so the same code runs on a laptop (`--local`) and in Azure.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Protocol

import pandas as pd

# <repo>/data/lake — git-ignored, mirrors the Data Lake layout (container/path).
LOCAL_ROOT = Path(__file__).resolve().parents[2] / "data" / "lake"


class Sink(Protocol):
    def write_bytes(self, container: str, path: str, data: bytes) -> str:
        """Write data and return where it went (for logs and the ADF response)."""
        ...


class LocalSink:
    def __init__(self, root: Path = LOCAL_ROOT) -> None:
        self.root = root

    def write_bytes(self, container: str, path: str, data: bytes) -> str:
        target = self.root / container / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)


class LakeSink:
    """Data Lake (ADLS Gen2) using the Function App's managed identity, or your az login locally."""

    def __init__(self, client=None) -> None:
        if client is None:
            from etl.common import lake_client

            client = lake_client()
        self.client = client

    def write_bytes(self, container: str, path: str, data: bytes) -> str:
        file_client = self.client.get_file_system_client(container).get_file_client(path)
        file_client.upload_data(data, overwrite=True)
        return f"{container}/{path}"


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialize to parquet that Azure Data Factory can read.

    pandas stores datetimes in nanoseconds, which ADF's parquet reader does not support
    (it reads them as plain Int64). Write millisecond timestamps instead.
    """
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, coerce_timestamps="ms", allow_truncated_timestamps=True)
    return buffer.getvalue()