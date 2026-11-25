"""Unit tests for grouping Azure SQL route x airline x month rows into Cosmos documents.

Pure Python: no SQL connection, no Cosmos client, no network.
"""

from etl.transform_routes import build_route_documents, group_route_rows


def row(**overrides):
    base = dict(
        route_key=1,
        origin="JFK",
        dest="LAX",
        month_key=202401,
        carrier_code="AA",
        flights=100,
        cancelled=10,
        diverted=0,
        completed_flights=90,
        on_time_rate=0.8,
        avg_arr_delay_min=5.0,
        p90_arr_delay_min=20.0,
        weather_delay_share=0.1,
    )
    base.update(overrides)
    return base


def test_group_route_rows_groups_by_origin_dest_month():
    grouped = group_route_rows([row(), row(dest="SFO"), row(month_key=202402)])

    assert set(grouped) == {("JFK", "LAX", 202401), ("JFK", "SFO", 202401), ("JFK", "LAX", 202402)}


def test_build_route_documents_sums_totals_across_airlines():
    rows = [
        row(carrier_code="AA", flights=100, cancelled=10, diverted=0, completed_flights=90,
            on_time_rate=0.8),
        row(carrier_code="DL", flights=50, cancelled=0, diverted=0, completed_flights=50,
            on_time_rate=0.6),
    ]  # fmt: skip
    [doc] = build_route_documents(group_route_rows(rows))

    assert doc["id"] == "JFK-LAX-202401"
    assert doc["route_key"] == 1
    assert doc["totals"]["flights"] == 150
    assert doc["totals"]["cancelled"] == 10
    assert doc["totals"]["completed_flights"] == 140
    # Weighted by completed_flights: (0.8*90 + 0.6*50) / 140
    assert doc["totals"]["on_time_rate"] == round((0.8 * 90 + 0.6 * 50) / 140, 4)
    assert [a["carrier_code"] for a in doc["by_airline"]] == ["AA", "DL"]


def test_cancel_and_divert_rate_are_over_total_flights_not_completed():
    [doc] = build_route_documents(group_route_rows([row(flights=100, cancelled=10, diverted=5)]))

    assert doc["totals"]["cancel_rate"] == 0.1
    assert doc["totals"]["divert_rate"] == 0.05


def test_weighted_average_ignores_rows_with_no_completed_flights():
    # A fully-cancelled airline-month contributes no weight, so it must not pull the average down.
    rows = [
        row(carrier_code="AA", flights=10, cancelled=10, diverted=0, completed_flights=0,
            on_time_rate=0.9),
        row(carrier_code="DL", flights=50, cancelled=0, diverted=0, completed_flights=50,
            on_time_rate=0.5),
    ]  # fmt: skip
    [doc] = build_route_documents(group_route_rows(rows))

    assert doc["totals"]["on_time_rate"] == 0.5


def test_all_flights_cancelled_has_no_rate_but_full_cancel_rate():
    rows = [row(flights=5, cancelled=5, diverted=0, completed_flights=0, on_time_rate=None)]
    [doc] = build_route_documents(group_route_rows(rows))

    assert doc["totals"]["on_time_rate"] is None
    assert doc["totals"]["cancel_rate"] == 1.0


def test_document_ids_are_unique_per_route_and_month():
    rows = [row(), row(dest="SFO"), row(month_key=202402)]
    documents = build_route_documents(group_route_rows(rows))

    ids = [doc["id"] for doc in documents]
    assert len(ids) == len(set(ids)) == 3
