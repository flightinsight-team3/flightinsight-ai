import pytest

from etl.common import parse_month_key, parse_year


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
