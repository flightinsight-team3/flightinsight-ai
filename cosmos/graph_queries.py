# Read-only alternative route queries from Azure Cosmos DB Gremlin.
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from gremlin_python.driver import client, serializer


# Load existing Gremlin connection settings.
ENV_FILE = (
    Path(__file__).resolve().parent.parent
    / "functions"
    / ".gremlin.env"
)
load_dotenv(ENV_FILE)


def get_gremlin_client():
    # Connect to the existing Cosmos DB Gremlin graph.

    host = os.environ["GREMLIN_HOST"]
    database = os.environ["GREMLIN_DATABASE"]
    graph = os.environ["GREMLIN_GRAPH"]
    key = os.environ["GREMLIN_KEY"]

    endpoint = f"wss://{host}:443/"
    username = f"/dbs/{database}/colls/{graph}"

    return client.Client(
        endpoint,
        "g",
        username=username,
        password=key,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )


def find_alternative_routes(origin, dest, year=2024):
    """
    Find historical one-stop alternative routes.

    Path: origin -> connecting airport -> destination.

    Results are historical network candidates, not
    confirmed flight connections or bookable itineraries.
    """

    origin = origin.strip().upper()
    dest = dest.strip().upper()
    year = int(year)

    for airport in (origin, dest):
        if (
            len(airport) != 3
            or not airport.isascii()
            or not airport.isalpha()
        ):
            raise ValueError("Airport codes must be 3-letter IATA codes")

    if origin == dest:
        raise ValueError("Origin and destination must be different")

    if not 2000 <= year <= 2100:
        raise ValueError("Invalid year")

    gremlin_client = get_gremlin_client()

    try:
        # Retrieve directed route edges for the requested year.
        query = """
             g.E().hasLabel('route').has('year', year)
            .project('origin', 'dest', 'flights', 'on_time_rate')
            .by(outV().id())
            .by(inV().id())
            .by(values('flights'))
            .by(values('on_time_rate'))
        """

        edges = gremlin_client.submit(
            query,
            bindings={"year": year},
        ).all().result()

        # Build directed airport connections.
        outgoing = {}

        for edge in edges:
            source = str(edge["origin"]).upper()
            target = str(edge["dest"]).upper()

            outgoing.setdefault(source, []).append({
                "dest": target,
                "flights": edge.get("flights"),
                "on_time_rate": edge.get("on_time_rate"),
            })

        alternatives = []
        seen_connections = set()

        # Find origin -> connection -> destination.
        for first_leg in outgoing.get(origin, []):
            connection = first_leg["dest"]

            if connection in (origin, dest):
                continue

            for second_leg in outgoing.get(connection, []):
                if second_leg["dest"] != dest:
                    continue

                if connection in seen_connections:
                    continue

                seen_connections.add(connection)

                alternatives.append({
                    "origin": origin,
                    "connection": connection,
                    "dest": dest,
                    "path": [origin, connection, dest],
                    "stops": 1,
                    "legs": [
                        {
                            "origin": origin,
                            "dest": connection,
                            "flights": first_leg["flights"],
                            "on_time_rate": first_leg["on_time_rate"],
                        },
                        {
                            "origin": connection,
                            "dest": dest,
                            "flights": second_leg["flights"],
                            "on_time_rate": second_leg["on_time_rate"],
                        },
                    ],
                })

        return {
            "origin": origin,
            "dest": dest,
            "year": year,
            "alternative_routes": alternatives,
            "count": len(alternatives),
        }

    finally:
        gremlin_client.close()


if __name__ == "__main__":
    result = find_alternative_routes("ATL", "AUS", 2024)
    print(json.dumps(result, indent=2))
