"""Gremlin graph loader (ADF has no Gremlin connector, so this runs as a Function).

load_route_edges: read yearly route reliability from agg_route_monthly and upsert
                  airport / airline vertices and route / operates_at edges.
                  See cosmos/graph-model.md.
"""


def load_route_edges(year: int) -> dict:
    raise NotImplementedError("graph.load_route_edges")
