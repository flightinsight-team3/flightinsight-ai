import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_graph.json"


def find_alternative_routes(origin, dest):
    # Read the airport network
    with open(DATA_FILE, encoding="utf-8") as file:
        graph = json.load(file)

    origin = origin.upper()
    dest = dest.upper()

    routes = graph["routes"]
    alternatives = []

    # Find the first flight leg
    for first_leg in routes:
        if first_leg["origin"] != origin:
            continue

        connecting_airport = first_leg["dest"]

        if connecting_airport in (origin, dest):
            continue

        # Find the second flight leg
        for second_leg in routes:
            if second_leg["origin"] == connecting_airport and second_leg["dest"] == dest:
                alternatives.append(
                    {
                        "origin": origin,
                        "connection": connecting_airport,
                        "dest": dest,
                        "path": [origin, connecting_airport, dest],
                        "stops": 1,
                    }
                )

    return {
        "origin": origin,
        "dest": dest,
        "alternative_routes": alternatives,
        "count": len(alternatives),
    }


if __name__ == "__main__":
    result = find_alternative_routes("SEA", "MIA")
    print(json.dumps(result, indent=2))
