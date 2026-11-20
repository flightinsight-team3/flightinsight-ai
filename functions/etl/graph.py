"""Gremlin graph loader for FlightInsight.

Yearly route reliability is calculated from dbo.fact_flights.
Airport and airline metadata comes from Azure SQL dimension tables.

Graph model:
- Airport and Airline vertices
- Route and operates_at edges

See cosmos/graph-model.md.
"""


def fetch_airports(connection):
    # Read airport data from Azure SQL without modifying it.
    query = """
        SELECT
            a.iata_code,
            a.airport_name,
            a.city,
            g.state_code,
            a.hub_type,
            a.is_top30
        FROM dbo.dim_airports AS a
        JOIN dbo.dim_geography AS g
            ON a.geo_key = g.geo_key
    """

    cursor = connection.cursor()
    cursor.execute(query)

    columns = [column[0] for column in cursor.description]

    return [
        dict(zip(columns, row, strict=True))
        for row in cursor.fetchall()
    ]



def build_airport_vertex(row: dict) -> dict:
    # Convert one SQL airport row into a Gremlin vertex record.
    iata = str(row["iata_code"] or "").strip().upper()
    state = str(row["state_code"] or "").strip().upper()

    if not iata or not state:
        raise ValueError("Airport must have an IATA code and state code")

    return {
        "id": iata,
        "label": "airport",
        "pk": state,
        "airport_name": row["airport_name"],
        "city": row["city"],
        "state_code": state,
        "hub_type": row["hub_type"],
        "is_top30": bool(row["is_top30"]),
    }


def build_airline_vertex(row: dict) -> dict:
    # Convert one SQL airline row into a Gremlin vertex record.
    carrier = str(row["carrier_code"] or "").strip().upper()

    if not carrier:
        raise ValueError("Airline must have a carrier code")

    return {
        "id": carrier,
        "label": "airline",
        "pk": "airline",
        "airline_name": row["airline_name"],
    }



def build_route_edge(row: dict, year: int) -> dict:
    # Convert one yearly SQL route summary into a Graph edge record.

    route_key = int(row["route_key"])
    origin = str(row["origin"] or "").strip().upper()
    destination = str(row["destination"] or "").strip().upper()

    if route_key <= 0:
        raise ValueError("route_key must be positive")

    if not origin or not destination:
        raise ValueError("Route must have origin and destination airports")

    flights = int(row["flights"])
    completed = int(row["completed_flights"])
    on_time = int(row["on_time_flights"])

    if not (0 <= on_time <= completed <= flights):
        raise ValueError("Invalid route flight counts")

    on_time_rate = (
        on_time / completed if completed > 0 else None
    )

    return {
        "id": f"route-{route_key}-{year}",
        "label": "route",
        "route_key": route_key,
        "year": year,
        "outV": origin,
        "inV": destination,
        "flights": flights,
        "completed_flights": completed,
        "on_time_flights": on_time,
        "on_time_rate": on_time_rate,
        "avg_arr_delay_min": (
            float(row["avg_arr_delay_min"])
            if row["avg_arr_delay_min"] is not None
            else None
        ),
        "cancel_rate": (
            float(row["cancel_rate"])
            if row["cancel_rate"] is not None
            else None
        ),
        "distance_mi": (
            float(row["distance_mi"])
            if row["distance_mi"] is not None
            else None
        ),
        "first_date_key": row["first_date_key"],
        "last_date_key": row["last_date_key"],
    }



def fetch_route_stats(connection, year: int) -> list[dict]:
    # Read route statistics for a year from Azure SQL (read-only)."""

    year = int(year)

    if not 2000 <= year <= 2100:
        raise ValueError("Invalid year")

    query = """
        WITH route_stats AS (
            SELECT
                route_key,
                COUNT(*) AS flights,

                SUM(CASE
                    WHEN is_cancelled = 1 THEN 1 ELSE 0
                END) AS cancelled_flights,

                SUM(CASE
                    WHEN is_cancelled = 0
                     AND is_diverted = 0
                     AND arr_delay_min IS NOT NULL
                    THEN 1 ELSE 0
                END) AS completed_flights,

                SUM(CASE
                    WHEN is_cancelled = 0
                     AND is_diverted = 0
                     AND arr_delay_min < 15
                    THEN 1 ELSE 0
                END) AS on_time_flights,

                AVG(CASE
                    WHEN is_cancelled = 0
                     AND is_diverted = 0
                     AND arr_delay_min IS NOT NULL
                    THEN CAST(arr_delay_min AS DECIMAL(18, 4))
                END) AS avg_arr_delay_min,

                MIN(date_key) AS first_date_key,
                MAX(date_key) AS last_date_key

            FROM dbo.fact_flights
            WHERE date_key >= ?
              AND date_key < ?
            GROUP BY route_key
        )
        SELECT
            r.route_key,
            origin.iata_code AS origin,
            dest.iata_code AS destination,
            r.distance_mi,

            s.flights,
            s.completed_flights,
            s.on_time_flights,

            CAST(
                1.0 * s.on_time_flights
                / NULLIF(s.completed_flights, 0)
                AS DECIMAL(9, 4)
            ) AS on_time_rate,

            CAST(
                s.avg_arr_delay_min AS DECIMAL(10, 2)
            ) AS avg_arr_delay_min,

            CAST(
                1.0 * s.cancelled_flights
                / NULLIF(s.flights, 0)
                AS DECIMAL(9, 4)
            ) AS cancel_rate,

            s.first_date_key,
            s.last_date_key

        FROM route_stats AS s
        JOIN dbo.dim_routes AS r
            ON s.route_key = r.route_key
        JOIN dbo.dim_airports AS origin
            ON r.origin_airport_key = origin.airport_key
        JOIN dbo.dim_airports AS dest
            ON r.dest_airport_key = dest.airport_key

        ORDER BY r.route_key
    """

    start_date = year * 10000 + 101
    end_date = (year + 1) * 10000 + 101

    cursor = connection.cursor()
    cursor.execute(query, (start_date, end_date))

    columns = [column[0] for column in cursor.description]

    return [
        dict(zip(columns, row, strict=True))
        for row in cursor.fetchall()
    ]


def load_route_edges(year: int) -> dict:
    raise NotImplementedError("graph.load_route_edges")

def upsert_airport_vertex(gremlin_client, vertex: dict) -> str:
    # Create an airport vertex if absent; otherwise skip it.

    airport_id = vertex["id"]
    partition_key = vertex["pk"]

    existing = gremlin_client.submit(
        "g.V().has('airport', 'id', airport_id)"
        ".has('pk', partition_key).count()",
        bindings={
            "airport_id": airport_id,
            "partition_key": partition_key,
        },
    ).all().result()[0]

    if existing:
        return "skipped"

    query = """
        g.addV('airport')
         .property('id', airport_id)
         .property('pk', partition_key)
         .property('airport_name', airport_name)
         .property('city', city)
         .property('state_code', state_code)
         .property('hub_type', hub_type)
         .property('is_top30', is_top30)
    """

    gremlin_client.submit(
        query,
        bindings={
            "airport_id": airport_id,
            "partition_key": partition_key,
            "airport_name": vertex["airport_name"],
            "city": vertex["city"],
            "state_code": vertex["state_code"],
            "hub_type": vertex["hub_type"],
            "is_top30": vertex["is_top30"],
        },
    ).all().result()

    return "created"


def upsert_route_edge(gremlin_client, edge: dict) -> str:
    # Create a route edge if absent; otherwise skip it.

    edge_id = edge["id"]

    # Check whether this route edge already exists.
    existing = gremlin_client.submit(
        "g.E().has('id', edge_id).count()",
        bindings={"edge_id": edge_id},
    ).all().result()[0]

    if existing:
        return "skipped"

    # Find the source and destination airport vertices.
    # Their partition keys may differ.
    query = """
        g.V().has('airport', 'id', origin)
         .addE('route')
         .to(g.V().has('airport', 'id', destination))
         .property('id', edge_id)
         .property('route_key', route_key)
         .property('year', year)
         .property('flights', flights)
         .property('completed_flights', completed_flights)
         .property('on_time_flights', on_time_flights)
         .property('on_time_rate', on_time_rate)
         .property('avg_arr_delay_min', avg_arr_delay_min)
         .property('cancel_rate', cancel_rate)
         .property('distance_mi', distance_mi)
         .property('first_date_key', first_date_key)
         .property('last_date_key', last_date_key)
    """

    bindings = {
        "origin": edge["outV"],
        "destination": edge["inV"],
        "edge_id": edge_id,
        "route_key": edge["route_key"],
        "year": edge["year"],
        "flights": edge["flights"],
        "completed_flights": edge["completed_flights"],
        "on_time_flights": edge["on_time_flights"],
        "on_time_rate": edge["on_time_rate"],
        "avg_arr_delay_min": edge["avg_arr_delay_min"],
        "cancel_rate": edge["cancel_rate"],
        "distance_mi": edge["distance_mi"],
        "first_date_key": edge["first_date_key"],
        "last_date_key": edge["last_date_key"],
    }

    gremlin_client.submit(query, bindings=bindings).all().result()

    return "created"