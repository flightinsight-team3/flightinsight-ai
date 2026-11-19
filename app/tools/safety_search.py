"""search_safety_reports: semantic search over NASA ASRS reports (Cosmos DB vector search).

The question is embedded with the same Ollama model as the reports ("search_query: " prefix),
then Cosmos returns the most similar reports, optionally filtered by month, airport or aircraft.
"""

from __future__ import annotations

from app.asrs.parse import parse_month

DEFAULT_TOP_K = 5
MAX_TOP_K = 20
FILTERS = ("month_key", "start_month", "end_month", "airport_code", "aircraft_family")
FIELDS = (
    "id",
    "month_key",
    "airport_code",
    "aircraft_family",
    "flight_phase",
    "weather",
    "anomaly",
    "reporter",
    "synopsis",
    "narrative",
)


def search_safety_reports(
    query: str,
    filters: dict | None = None,
    top_k: int = DEFAULT_TOP_K,
    *,
    container=None,
    embedder=None,
) -> list[dict]:
    """Return the top_k ASRS reports most similar to `query`, most similar first.

    filters (all optional): month_key (202403), start_month / end_month (inclusive range),
    airport_code ("ORD"), aircraft_family ("B737", "A320", "CRJ", "ERJ", ...).
    Each result has the report fields plus `similarity` (cosine, higher is more similar).
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    filters = normalize_filters(filters or {})
    if embedder is None:
        from app.asrs.embeddings import OllamaEmbedder

        embedder = OllamaEmbedder()
    if container is None:
        from app.asrs.store import asrs_container

        container = asrs_container()

    sql, parameters = build_query(embedder.embed_query(query), filters, top_k)
    options: dict = {"parameters": parameters}
    if "month_key" in filters:
        options["partition_key"] = filters["month_key"]  # single-partition query
    else:
        options["enable_cross_partition_query"] = True
    return list(container.query_items(sql, **options))


def build_query(vector: list[float], filters: dict, top_k: int) -> tuple[str, list[dict]]:
    """Cosmos SQL for a filtered vector search. Values are always passed as parameters."""
    if not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"top_k must be an integer from 1 to {MAX_TOP_K}, got {top_k!r}")
    conditions, parameters = [], [{"name": "@vector", "value": vector}]
    comparisons = {
        "month_key": "c.month_key = @month_key",
        "start_month": "c.month_key >= @start_month",
        "end_month": "c.month_key <= @end_month",
        "airport_code": "c.airport_code = @airport_code",
        "aircraft_family": "c.aircraft_family = @aircraft_family",
    }
    for name in FILTERS:
        if name in filters:
            conditions.append(comparisons[name])
            parameters.append({"name": f"@{name}", "value": filters[name]})

    columns = ", ".join(f"c.{f}" for f in FIELDS)
    distance = "VectorDistance(c.narrative_vector, @vector)"
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = (
        f"SELECT TOP {top_k} {columns}, {distance} AS similarity FROM c{where} ORDER BY {distance}"
    )
    return sql, parameters


def normalize_filters(filters: dict) -> dict:
    """Validate filter names and values; drop empty ones. Unknown names are an error, so a
    mistyped filter from the LLM is reported instead of silently ignored."""
    unknown = set(filters) - set(FILTERS)
    if unknown:
        raise ValueError(f"Unknown filters {sorted(unknown)}; allowed: {list(FILTERS)}")
    clean: dict = {}
    for name, value in filters.items():
        if value is None or value == "":
            continue
        if name in ("month_key", "start_month", "end_month"):
            month = parse_month(str(value))
            if month is None:
                raise ValueError(f"{name} must be a month like 202403, got {value!r}")
            clean[name] = month
        else:
            clean[name] = str(value).strip().upper()
    return clean
