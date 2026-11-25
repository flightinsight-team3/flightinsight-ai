"""search_safety_reports query building, with a fake embedder and container. No network."""

import pytest

from app.tools.safety_search import build_query, search_safety_reports


class FakeEmbedder:
    def __init__(self):
        self.questions = []

    def embed_query(self, question):
        self.questions.append(question)
        return [0.5, 0.5]


class FakeContainer:
    def __init__(self, results=()):
        self.results, self.calls = list(results), []

    def query_items(self, query, **options):
        self.calls.append((query, options))
        return iter(self.results)


def search(filters=None, top_k=5, results=()):
    embedder, container = FakeEmbedder(), FakeContainer(results)
    found = search_safety_reports(
        "rushed by delays", filters, top_k, container=container, embedder=embedder
    )
    return found, embedder, container


def test_search_without_filters_is_cross_partition_and_ordered_by_similarity():
    found, embedder, container = search(results=[{"id": "1", "similarity": 0.9}])

    sql, options = container.calls[0]
    assert found == [{"id": "1", "similarity": 0.9}]
    assert embedder.questions == ["rushed by delays"]
    assert sql.startswith("SELECT TOP 5 c.id,")
    assert "WHERE" not in sql
    assert sql.endswith("ORDER BY VectorDistance(c.narrative_vector, @vector)")
    assert options["enable_cross_partition_query"] is True
    assert options["parameters"] == [{"name": "@vector", "value": [0.5, 0.5]}]


def test_month_filter_targets_one_partition():
    _, _, container = search({"month_key": "2024-03"})
    sql, options = container.calls[0]
    assert "WHERE c.month_key = @month_key" in sql
    assert options["partition_key"] == 202403
    assert "enable_cross_partition_query" not in options


def test_range_airport_and_aircraft_filters_are_parameters():
    filters = {
        "start_month": 202401,
        "end_month": 202403,
        "airport_code": "sea",
        "aircraft_family": "b737",
    }
    _, _, container = search(filters)
    sql, options = container.calls[0]

    assert (
        "WHERE c.month_key >= @start_month AND c.month_key <= @end_month "
        "AND c.airport_code = @airport_code AND c.aircraft_family = @aircraft_family"
    ) in sql
    params = {p["name"]: p["value"] for p in options["parameters"]}
    assert params["@airport_code"] == "SEA"
    assert params["@aircraft_family"] == "B737"
    assert "SEA" not in sql  # values never pasted into the SQL text


def test_empty_filter_values_are_ignored():
    _, _, container = search({"airport_code": "", "month_key": None})
    assert "WHERE" not in container.calls[0][0]


@pytest.mark.parametrize(
    "filters,message",
    [({"airport": "ORD"}, "Unknown filters"), ({"month_key": "March"}, "month like")],
)
def test_bad_filters_raise(filters, message):
    with pytest.raises(ValueError, match=message):
        search(filters)


@pytest.mark.parametrize("top_k", [0, 21, "5"])
def test_top_k_is_bounded(top_k):
    with pytest.raises(ValueError, match="top_k"):
        build_query([0.1], {}, top_k)


def test_empty_query_raises():
    with pytest.raises(ValueError, match="empty"):
        search_safety_reports(" ", container=FakeContainer(), embedder=FakeEmbedder())
