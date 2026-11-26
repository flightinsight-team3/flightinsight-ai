"""Gremlin graph loader for FlightInsight.

Yearly route reliability is calculated from dbo.fact_flights.
Airport and airline metadata comes from Azure SQL dimension tables.

Graph model:
- Airport and Airline vertices
- Route and operates_at edges

See cosmos/graph-model.md.
"""

import logging
import math
import os

from gremlin_python.driver import client, serializer

from etl.cosmos_sync import get_sql_connection


def get_gremlin_client():
    # Connect to the existing Cosmos DB Gremlin graph.
    host = os.environ["GREMLIN_HOST"]
    database = os.environ["GREMLIN_DATABASE"]
    graph = os.environ["GREMLIN_GRAPH"]
    key = os.environ["GREMLIN_KEY"]

    return client.Client(
        f"wss://{host}:443/",
        "g",
        username=f"/dbs/{database}/colls/{graph}",
        password=key,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )

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
        WHERE a.is_top30 = 1
    """

    cursor = connection.cursor()
    cursor.execute(query)

    columns = [column[0] for column in cursor.description]

    return [
        dict(zip(columns, row, strict=True))
        for row in cursor.fetchall()
    ]

def fetch_airlines(connection) -> list[dict]:
    # Read airline data from Azure SQL.
    query = """
        SELECT
            carrier_code,
            airline_name
        FROM dbo.dim_airlines
    """

    cursor = connection.cursor()
    cursor.execute(query)

    columns = [column[0] for column in cursor.description]

    return [
        dict(zip(columns, row, strict=True))
        for row in cursor.fetchall()
    ]

def fetch_operates_at_stats(connection, year: int) -> list[dict]:
    # Read annual airline departure statistics by airport.
    year = int(year)

    if not 2000 <= year <= 2100:
        raise ValueError("Invalid year")

    query = """
        WITH airline_airport_stats AS (
            SELECT
                a.carrier_code,
                origin.iata_code,
                COUNT(*) AS flights
            FROM dbo.fact_flights AS f
            JOIN dbo.dim_airlines AS a
                ON f.airline_key = a.airline_key
            JOIN dbo.dim_routes AS r
                ON f.route_key = r.route_key
            JOIN dbo.dim_airports AS origin
                ON r.origin_airport_key = origin.airport_key
            WHERE f.date_key >= ?
              AND f.date_key < ?
            GROUP BY
                a.carrier_code,
                origin.iata_code
        )
        SELECT
            carrier_code,
            iata_code,
            flights,
            1.0 * flights / NULLIF(
                SUM(flights) OVER (PARTITION BY iata_code), 0
            ) AS share_of_airport
        FROM airline_airport_stats
        ORDER BY iata_code, carrier_code
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


def fetch_existing_edges(gremlin_client, label: str, year: int) -> dict:
    # Read existing annual edges in one query.
    rows = gremlin_client.submit(
        "g.E().hasLabel(edge_label).has('year', edge_year)",
        bindings={
            "edge_label": label,
            "edge_year": year,
        },
    ).all().result()

    existing = {}

    for row in rows:
        edge_id = row["id"]

        if edge_id in existing:
            raise ValueError(f"Duplicate edge ID: {edge_id}")

        existing[edge_id] = row

    return existing


def edge_is_unchanged(edge: dict, existing: dict) -> bool:
    # Compare SQL statistics with existing graph properties.
    properties = existing.get("properties", {})

    for key, expected in edge.items():
        if key in {
            "id", "label", "outV", "inV",
            "airline_id", "airport_id",
        }:
            continue

        if key not in properties:
            return False

        actual = properties[key]

        if isinstance(expected, float):
            if not isinstance(actual, (int, float)):
                return False

            if not math.isclose(
                actual,
                expected,
                rel_tol=1e-9,
                abs_tol=1e-12,
            ):
                return False

        elif actual != expected:
            return False

    return True


def load_route_edges(year: int) -> dict:
    # Synchronize annual graph data from Azure SQL.
    year = int(year)

    if not 2000 <= year <= 2100:
        raise ValueError("Invalid year")

    # Read all required data from Azure SQL.
    connection = get_sql_connection()

    try:
        airport_rows = fetch_airports(connection)
        airline_rows = fetch_airlines(connection)
        route_rows = fetch_route_stats(connection, year)
        operates_at_rows = fetch_operates_at_stats(connection, year)
    finally:
        connection.close()

    # Transform SQL rows into graph records.
    airport_vertices = [
        build_airport_vertex(row) for row in airport_rows
    ]

    airline_vertices = [
        build_airline_vertex(row) for row in airline_rows
    ]

    route_edges = [
        build_route_edge(row, year) for row in route_rows
    ]

    operates_at_edges = [
        build_operates_at_edge(row, year)
        for row in operates_at_rows
    ]

    if not all([
        airport_vertices,
        airline_vertices,
        route_edges,
        operates_at_edges,
    ]):
        raise ValueError("Missing graph data; refusing to sync.")

    # Track synchronization results.
    results = {
        "airport_vertices": {
            "created": 0, "updated": 0, "skipped": 0
        },
        "airline_vertices": {
            "created": 0, "updated": 0, "skipped": 0
        },
        "route_edges": {
            "created": 0, "updated": 0, "skipped": 0
        },
        "operates_at_edges": {
            "created": 0, "updated": 0, "skipped": 0
        },
    }

    gremlin_client = get_gremlin_client()

    try:
        for vertex in airport_vertices:
            status = upsert_airport_vertex(gremlin_client, vertex)
            results["airport_vertices"][status] += 1

        for vertex in airline_vertices:
            status = upsert_airline_vertex(gremlin_client, vertex)
            results["airline_vertices"][status] += 1

        # Read existing annual edges before synchronization.
        existing_routes = fetch_existing_edges(
            gremlin_client, "route", year
        )

        existing_operates_at = fetch_existing_edges(
            gremlin_client, "operates_at", year
        )

        # Synchronize route edges only when necessary.
        for edge in route_edges:
            existing = existing_routes.get(edge["id"])

            if existing is not None and edge_is_unchanged(edge, existing):
                status = "skipped"
            else:
                status = upsert_route_edge(gremlin_client, edge)

            results["route_edges"][status] += 1

        logging.info(
            "Route synchronization completed: %s",
            results["route_edges"],
        )

        # Synchronize airline-to-airport edges only when necessary.
        for edge in operates_at_edges:
            existing = existing_operates_at.get(edge["id"])

            if existing is not None and edge_is_unchanged(edge, existing):
                status = "skipped"
            else:
                status = upsert_operates_at_edge(gremlin_client, edge)

            results["operates_at_edges"][status] += 1

        logging.info(
            "Operates_at synchronization completed: %s",
            results["operates_at_edges"],
        )

    finally:
        gremlin_client.close()

    return {
        "year": year,
        **results,
    }

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


    if existing > 1:
        raise ValueError(f"Duplicate route edge ID: {edge_id}")

    if existing == 1:
        query = """
            g.E().has('id', edge_id)
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

        gremlin_client.submit(
            query,
            bindings={
                "edge_id": edge_id,
                "flights": edge["flights"],
                "completed_flights": edge["completed_flights"],
                "on_time_flights": edge["on_time_flights"],
                "on_time_rate": edge["on_time_rate"],
                "avg_arr_delay_min": edge["avg_arr_delay_min"],
                "cancel_rate": edge["cancel_rate"],
                "distance_mi": edge["distance_mi"],
                "first_date_key": edge["first_date_key"],
                "last_date_key": edge["last_date_key"],
            },
        ).all().result()

        return "updated"

    # Resolve each airport's partition key before creating the edge.
    partition_keys = {}

    for airport_id in (edge["outV"], edge["inV"]):
        matches = gremlin_client.submit(
            "g.V().has('airport', 'id', airport_id).values('pk')",
            bindings={"airport_id": airport_id},
        ).all().result()

        if len(matches) != 1:
            raise ValueError(
                f"Expected one partition key for {airport_id}, "
                f"got {len(matches)}"
            )

        partition_keys[airport_id] = matches[0]

    query = """
        g.V().has('airport', 'id', origin)
         .has('pk', origin_pk)
         .addE('route')
         .to(
             g.V().has('airport', 'id', destination)
              .has('pk', destination_pk)
         )
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
        "origin_pk": partition_keys[edge["outV"]],
        "destination": edge["inV"],
        "destination_pk": partition_keys[edge["inV"]],
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



def upsert_airline_vertex(gremlin_client, vertex: dict) -> str:
    # Create an airline vertex if absent; otherwise skip it.

    airline_id = vertex["id"]
    partition_key = vertex["pk"]

    # Check whether this airline vertex already exists.
    existing = gremlin_client.submit(
        "g.V().has('airline', 'id', airline_id)"
        ".has('pk', partition_key).count()",
        bindings={
            "airline_id": airline_id,
            "partition_key": partition_key,
        },
    ).all().result()[0]

    if existing:
        return "skipped"

    # Create one airline vertex.
    query = """
        g.addV('airline')
         .property('id', airline_id)
         .property('pk', partition_key)
         .property('airline_name', airline_name)
    """

    gremlin_client.submit(
        query,
        bindings={
            "airline_id": airline_id,
            "partition_key": partition_key,
            "airline_name": vertex["airline_name"],
        },
    ).all().result()

    return "created"


def build_operates_at_edge(row: dict, year: int) -> dict:
    # Build an annual airline-to-airport edge from SQL statistics.

    carrier = str(row["carrier_code"] or "").strip().upper()
    airport = str(row["iata_code"] or "").strip().upper()

    if not carrier or not airport:
        raise ValueError("Airline and airport codes are required")

    flights = int(row["flights"])
    share = float(row["share_of_airport"])

    if flights <= 0:
        raise ValueError("Flights must be positive")

    if not 0 < share <= 1:
        raise ValueError("share_of_airport must be between 0 and 1")

    return {
        "id": f"{carrier}-{airport}-{int(year)}",
        "label": "operates_at",
        "airline_id": carrier,
        "airport_id": airport,
        "flights": flights,
        "share_of_airport": share,
        "year": int(year),
    }


def upsert_operates_at_edge(gremlin_client, edge: dict) -> str:
    # Create or update one annual airline-to-airport edge.

    edge_id = edge["id"]
    airline_id = edge["airline_id"]
    airport_id = edge["airport_id"]

    # Check whether this edge already exists.
    existing = gremlin_client.submit(
        "g.E().has('id', edge_id).count()",
        bindings={"edge_id": edge_id},
    ).all().result()[0]

    if existing > 1:
        raise ValueError(f"Duplicate operates_at edge ID: {edge_id}")

    # If the edge exists, refresh its annual statistics.
    if existing == 1:
        query = """
            g.E().has('id', edge_id)
             .property('flights', flights)
             .property('share_of_airport', share_of_airport)
             .property('year', year)
        """

        gremlin_client.submit(
            query,
            bindings={
                "edge_id": edge_id,
                "flights": edge["flights"],
                "share_of_airport": edge["share_of_airport"],
                "year": edge["year"],
            },
        ).all().result()

        return "updated"

    # Find the airport's partition key.
    airport_partitions = gremlin_client.submit(
        """
        g.V().has('airport', 'id', airport_id)
         .values('pk')
        """,
        bindings={"airport_id": airport_id},
    ).all().result()

    if len(airport_partitions) != 1:
        raise ValueError(
            f"Expected one airport vertex for {airport_id}, "
            f"found {len(airport_partitions)}"
        )

    airport_pk = airport_partitions[0]

    # Create an edge from the airline to the airport.
    query = """
        g.V().has('airline', 'id', airline_id)
         .has('pk', 'airline')
         .addE('operates_at')
         .to(
             g.V().has('airport', 'id', airport_id)
              .has('pk', airport_pk)
         )
         .property('id', edge_id)
         .property('flights', flights)
         .property('share_of_airport', share_of_airport)
         .property('year', year)
    """

    gremlin_client.submit(
        query,
        bindings={
            "airline_id": airline_id,
            "airport_id": airport_id,
            "airport_pk": airport_pk,
            "edge_id": edge_id,
            "flights": edge["flights"],
            "share_of_airport": edge["share_of_airport"],
            "year": edge["year"],
        },
    ).all().result()

    return "created"