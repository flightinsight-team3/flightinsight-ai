"""get_route_delay_stats: monthly on-time statistics for one route, from Cosmos route_summaries.

Same signature as cosmos/route_queries.py (branch jingyangwang-cosmos-db), but it reuses the
app's Cosmos connection (key or `az login`) and validates its input, because the arguments
come from an LLM.
"""

from __future__ import annotations

import re

from app.asrs.parse import parse_month

AIRPORT = re.compile(r"[A-Z]{3}")


def get_route_delay_stats(
    origin: str,
    dest: str,
    start_month: int | str,
    end_month: int | str | None = None,
    *,
    container=None,
) -> list[dict]:
    """One route_summaries document per month for origin → dest, oldest first.

    end_month defaults to start_month. Returns [] when the route or months are not loaded.
    Each document has totals and by_airline stats (flights, on_time_rate, avg_arr_delay_min,
    cancel_rate, ...), see cosmos/schemas/route_summary.schema.json.
    """
    origin, dest = airport(origin, "origin"), airport(dest, "dest")
    start = month(start_month, "start_month")
    end = month(end_month, "end_month") if end_month not in (None, "") else start
    if start > end:
        raise ValueError(f"start_month {start} is after end_month {end}")
    if container is None:
        from app.asrs.store import route_container

        container = route_container()

    query = (
        "SELECT * FROM c WHERE c.origin = @origin AND c.dest = @dest "
        "AND c.month_key >= @start AND c.month_key <= @end ORDER BY c.month_key"
    )
    parameters = [
        {"name": "@origin", "value": origin},
        {"name": "@dest", "value": dest},
        {"name": "@start", "value": start},
        {"name": "@end", "value": end},
    ]
    docs = container.query_items(query, parameters=parameters, partition_key=origin)
    return [{k: v for k, v in doc.items() if not k.startswith("_")} for doc in docs]


def airport(value: str, name: str) -> str:
    code = str(value or "").strip().upper()
    if not AIRPORT.fullmatch(code):
        raise ValueError(f"{name} must be a 3-letter IATA airport code like ORD, got {value!r}")
    return code


def month(value: int | str, name: str) -> int:
    parsed = parse_month(str(value))
    if parsed is None:
        raise ValueError(f"{name} must be a month like 202401, got {value!r}")
    return parsed
