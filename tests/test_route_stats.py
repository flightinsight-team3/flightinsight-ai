"""get_route_delay_stats query building and validation, with a fake container. No network."""

import pytest

from app.tools.route_stats import get_route_delay_stats


class FakeContainer:
    def __init__(self, results=()):
        self.results, self.calls = list(results), []

    def query_items(self, query, **options):
        self.calls.append((query, options))
        return iter(self.results)


def test_single_month_query_targets_origin_partition():
    doc = {"id": "ATL-ORD-202401", "month_key": 202401, "_rid": "x", "_ts": 1}
    container = FakeContainer([doc])

    found = get_route_delay_stats(" atl", "ord", "2024-01", container=container)

    query, options = container.calls[0]
    assert found == [{"id": "ATL-ORD-202401", "month_key": 202401}]  # Cosmos "_" fields dropped
    assert options["partition_key"] == "ATL"
    params = {p["name"]: p["value"] for p in options["parameters"]}
    assert params == {"@origin": "ATL", "@dest": "ORD", "@start": 202401, "@end": 202401}
    assert "ATL" not in query and query.endswith("ORDER BY c.month_key")


def test_month_range():
    container = FakeContainer()
    assert get_route_delay_stats("ATL", "ORD", 202401, 202403, container=container) == []
    params = {p["name"]: p["value"] for p in container.calls[0][1]["parameters"]}
    assert (params["@start"], params["@end"]) == (202401, 202403)


@pytest.mark.parametrize(
    "args,message",
    [
        (("Atlanta", "ORD", 202401), "origin"),
        (("ATL", "KORD", 202401), "dest"),
        (("ATL", "ORD", "January"), "start_month"),
        (("ATL", "ORD", 202403, 202401), "after"),
    ],
)
def test_bad_arguments_raise(args, message):
    with pytest.raises(ValueError, match=message):
        get_route_delay_stats(*args, container=FakeContainer())
