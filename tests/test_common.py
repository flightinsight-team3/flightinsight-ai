import sys
import types

import pytest

from etl.common import parse_month_key, parse_year, sql_connection


@pytest.mark.parametrize("value", [202401, "202412", 200001])
def test_valid_month_keys(value):
    assert parse_month_key(value) == int(value)


@pytest.mark.parametrize("value", [202413, 202400, 19991, "abc", None])
def test_invalid_month_keys(value):
    with pytest.raises(ValueError):
        parse_month_key(value)


def test_year():
    assert parse_year("2024") == 2024
    with pytest.raises(ValueError):
        parse_year(1999)


@pytest.mark.parametrize(
    "database,setting_name",
    [("prod", "SQL_CONNECTION_STRING"), ("dev", "SQL_CONNECTION_STRING_DEV")],
)
def test_sql_connection_picks_prod_or_dev_connection_string(monkeypatch, database, setting_name):
    # Fake the pyodbc module itself (not just .connect): pyodbc needs a real ODBC driver
    # manager (unixODBC/Microsoft ODBC) installed to even import, which this test must not
    # require, so sql_connection()'s lazy `import pyodbc` picks up this fake from sys.modules.
    monkeypatch.setenv(setting_name, "fake-connection-string")
    seen = {}
    fake_pyodbc = types.SimpleNamespace(
        connect=lambda conn_str, autocommit: seen.update(conn_str=conn_str) or "connection"
    )
    monkeypatch.setitem(sys.modules, "pyodbc", fake_pyodbc)

    assert sql_connection(database) == "connection"
    assert seen["conn_str"] == "fake-connection-string"


def test_sql_connection_rejects_unknown_database():
    with pytest.raises(ValueError):
        sql_connection("staging")
