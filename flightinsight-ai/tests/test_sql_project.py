"""Guards the agreed star schema: every designed table must exist in the SQL project."""

import re
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[1] / "sql" / "FlightInsight"

STAR_SCHEMA = {
    "fact_flights", "fact_flight_delay_causes", "fact_flight_weather",
    "fact_weather_hourly", "fact_weather_daily",
    "agg_route_monthly",
    "dim_airports", "dim_routes", "dim_airlines", "dim_date", "dim_hour",
    "dim_geography", "dim_weather_stations", "dim_cancellation_reasons", "dim_delay_causes",
    "bridge_airport_station",
}

CREATE_TABLE = re.compile(r"CREATE\s+TABLE\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?", re.IGNORECASE)


def defined_tables() -> set[str]:
    names = set()
    for path in (SQL_DIR / "Tables").rglob("*.sql"):
        names.update(m.lower() for m in CREATE_TABLE.findall(path.read_text(encoding="utf-8")))
    return names


def test_star_schema_has_16_tables():
    assert len(STAR_SCHEMA) == 16


def test_every_star_schema_table_is_defined():
    missing = STAR_SCHEMA - defined_tables()
    assert not missing, f"Missing tables: {sorted(missing)}"


def test_one_table_per_file_named_after_it():
    for path in (SQL_DIR / "Tables").rglob("*.sql"):
        names = CREATE_TABLE.findall(path.read_text(encoding="utf-8"))
        found = [n.lower() for n in names]
        assert found == [path.stem], f"{path.name} should define only {path.stem}"
