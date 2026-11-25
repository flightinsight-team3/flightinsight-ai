"""Unit tests for the Azure SQL -> Cosmos DB sync wiring (etl/cosmos_sync.py).

No real network, no real Azure: the SQL connection and the Cosmos client are both faked, so
these catch wiring bugs (wrong setting name, wrong auth, wrong query shape) without needing
credentials or a live subscription. A real connectivity check still needs the deployed
Function App or a locally `az login`'d account with the Cosmos DB Data Contributor role.
"""

from decimal import Decimal

from etl import cosmos_sync

COLUMNS = [
    "route_key", "origin", "dest", "month_key", "carrier_code",
    "flights", "cancelled", "diverted", "on_time_rate",
    "avg_arr_delay_min", "p90_arr_delay_min", "weather_delay_share",
]  # fmt: skip


def sql_row(**overrides):
    base = dict(
        route_key=1, origin="JFK", dest="LAX", month_key=202401, carrier_code="AA",
        flights=100, cancelled=2, diverted=1, on_time_rate=Decimal("0.8"),
        avg_arr_delay_min=Decimal("5.5"), p90_arr_delay_min=Decimal("20.0"),
        weather_delay_share=Decimal("0.1"),
    )  # fmt: skip
    base.update(overrides)
    return tuple(base[c] for c in COLUMNS)


class FakeCursor:
    def __init__(self, rows):
        self.description = [(c,) for c in COLUMNS]
        self._rows = rows

    def execute(self, query):
        self.last_query = query

    def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_fetch_sql_rows_uses_the_shared_sql_connection(monkeypatch):
    cursor = FakeCursor([sql_row()])
    monkeypatch.setattr(
        cosmos_sync, "sql_connection", lambda database="prod": FakeConnection(cursor)
    )

    rows = cosmos_sync.fetch_sql_rows()

    assert rows == [dict(zip(COLUMNS, sql_row(), strict=True))]
    assert "agg_route_monthly" in cursor.last_query


def test_fetch_sql_rows_passes_the_database_through(monkeypatch):
    cursor = FakeCursor([sql_row()])
    seen = {}

    def fake_sql_connection(database="prod"):
        seen["database"] = database
        return FakeConnection(cursor)

    monkeypatch.setattr(cosmos_sync, "sql_connection", fake_sql_connection)

    cosmos_sync.fetch_sql_rows("dev")

    assert seen["database"] == "dev"


def test_prepare_rows_for_transform_converts_decimals_and_adds_completed_flights():
    row = dict(zip(COLUMNS, sql_row(), strict=True))

    [prepared] = cosmos_sync.prepare_rows_for_transform([row])

    assert isinstance(prepared["on_time_rate"], float)
    assert prepared["completed_flights"] == 100 - 2 - 1


def test_get_cosmos_container_reads_managed_identity_settings_not_a_key(monkeypatch):
    monkeypatch.setenv("COSMOS_NOSQL_ENDPOINT", "https://example-cosmos.documents.azure.com:443/")
    monkeypatch.setenv("COSMOS_NOSQL_DATABASE", "flightinsight")

    created = {}

    class FakeCredential:
        pass

    class FakeContainer:
        pass

    class FakeDatabase:
        def get_container_client(self, name):
            created["container"] = name
            return FakeContainer()

    class FakeCosmosClient:
        def __init__(self, endpoint, credential):
            created["endpoint"] = endpoint
            created["credential"] = credential

        def get_database_client(self, name):
            created["database"] = name
            return FakeDatabase()

    monkeypatch.setattr("azure.identity.DefaultAzureCredential", FakeCredential)
    monkeypatch.setattr("azure.cosmos.CosmosClient", FakeCosmosClient)

    container = cosmos_sync.get_cosmos_container()

    assert isinstance(container, FakeContainer)
    assert created["endpoint"] == "https://example-cosmos.documents.azure.com:443/"
    assert isinstance(created["credential"], FakeCredential)  # not a hardcoded key string
    assert created["database"] == "flightinsight"
    assert created["container"] == "route_summaries"


def test_sync_routes_to_cosmos_groups_airlines_into_one_document_per_route(monkeypatch):
    rows = [sql_row(), sql_row(carrier_code="DL")]
    cursor = FakeCursor(rows)
    monkeypatch.setattr(
        cosmos_sync, "sql_connection", lambda database="prod": FakeConnection(cursor)
    )

    upserted = []

    class FakeContainer:
        def upsert_item(self, body):
            upserted.append(body)

    monkeypatch.setattr(cosmos_sync, "get_cosmos_container", lambda: FakeContainer())

    result = cosmos_sync.sync_routes_to_cosmos()

    assert result == {"sql_rows": 2, "documents_synced": 1, "documents_failed": 0}
    assert upserted[0]["id"] == "JFK-LAX-202401"
    assert [a["carrier_code"] for a in upserted[0]["by_airline"]] == ["AA", "DL"]


def test_sync_routes_to_cosmos_counts_upsert_failures_instead_of_raising(monkeypatch):
    cursor = FakeCursor([sql_row(), sql_row(dest="SFO")])
    monkeypatch.setattr(
        cosmos_sync, "sql_connection", lambda database="prod": FakeConnection(cursor)
    )

    class FailingContainer:
        def upsert_item(self, body):
            if body["dest"] == "SFO":
                raise RuntimeError("boom")

    monkeypatch.setattr(cosmos_sync, "get_cosmos_container", lambda: FailingContainer())

    try:
        cosmos_sync.sync_routes_to_cosmos()
    except RuntimeError as exc:
        assert "1 documents" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when a document fails to sync")
