"""Helpers shared by every ETL step: input validation, settings, Azure clients."""

from __future__ import annotations

import os
from functools import lru_cache


def parse_month_key(value: object) -> int:
    """Validate a yyyymm month key such as 202401."""
    try:
        key = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"month_key must be an integer like 202401, got {value!r}") from exc
    year, month = divmod(key, 100)
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError(f"month_key out of range: {key}")
    return key


def parse_year(value: object) -> int:
    try:
        year = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"year must be an integer like 2024, got {value!r}") from exc
    if not 2000 <= year <= 2100:
        raise ValueError(f"year out of range: {year}")
    return year


def setting(name: str) -> str:
    """Read an app setting (Azure) or environment variable (laptop, from .env)."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing setting: {name}")
    return value


@lru_cache(maxsize=1)
def lake_client():
    """Data Lake client using the Function App's managed identity (or your az login locally)."""
    from azure.identity import DefaultAzureCredential
    from azure.storage.filedatalake import DataLakeServiceClient

    return DataLakeServiceClient(setting("DATA_LAKE_URL"), credential=DefaultAzureCredential())


def sql_connection():
    """New pyodbc connection to the prod database. Close it when done so the DB can auto-pause."""
    import pyodbc

    return pyodbc.connect(setting("SQL_CONNECTION_STRING"), autocommit=False)
