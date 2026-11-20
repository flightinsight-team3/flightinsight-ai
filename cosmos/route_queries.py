import os
from azure.cosmos import CosmosClient


def get_route_delay_stats(
    origin,
    dest,
    start_month,
    end_month,
    carrier_code=None,
):
    """
    Query historical monthly route delay statistics from Cosmos DB.

    Args:
        origin: 3-letter departure airport code, e.g. "ATL".
        dest: 3-letter arrival airport code, e.g. "AUS".
        start_month: Start month in YYYYMM format.
        end_month: End month in YYYYMM format.
        carrier_code: Optional airline code, e.g. "DL".

    Returns:
        A list of monthly statistics, sorted by month_key.

        Without carrier_code:
            Each record contains route totals and all airlines.

        With carrier_code:
            Each record contains only the selected airline's stats.

        Returns [] when no matching records are found.

    Note:
        This function queries historical data only.
        It does not predict future delays or provide live status.
    """

    # 1. Normalize and validate airport codes
    for name, value in (("origin", origin), ("dest", dest)):
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")

    origin = origin.strip().upper()
    dest = dest.strip().upper()

    for airport in (origin, dest):
        if (
            len(airport) != 3
            or not airport.isascii()
            or not airport.isalpha()
        ):
            raise ValueError("Airport codes must be 3 letters")

    if origin == dest:
        raise ValueError("origin and dest must be different")

    # 2. Validate month keys
    def validate_month(value, name):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be YYYYMM")

        if isinstance(value, int):
            month_key = value
        elif isinstance(value, str) and value.isascii() and value.isdigit():
            month_key = int(value)
        else:
            raise ValueError(f"{name} must be YYYYMM")

        year, month = divmod(month_key, 100)

        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError(f"{name} must be a valid YYYYMM")

        return month_key

    start_month = validate_month(start_month, "start_month")
    end_month = validate_month(end_month, "end_month")

    if start_month > end_month:
        raise ValueError("start_month cannot be after end_month")

    # 3. Normalize optional airline code
    if carrier_code is not None:
        if not isinstance(carrier_code, str):
            raise ValueError("carrier_code must be a string")

        carrier_code = carrier_code.strip().upper()

        if not carrier_code:
            raise ValueError("carrier_code cannot be empty")

    # 4. Read route documents from Cosmos DB
    client = CosmosClient(
        os.environ["COSMOS_ENDPOINT"],
        credential=os.environ["COSMOS_KEY"],
    )

    database = client.get_database_client("flightinsight")
    container = database.get_container_client("route_summaries")

    query = """
        SELECT *
        FROM c
        WHERE c.origin = @origin
          AND c.dest = @dest
          AND c.month_key >= @start_month
          AND c.month_key <= @end_month
    """

    parameters = [
        {"name": "@origin", "value": origin},
        {"name": "@dest", "value": dest},
        {"name": "@start_month", "value": start_month},
        {"name": "@end_month", "value": end_month},
    ]

    documents = list(
        container.query_items(
            query=query,
            parameters=parameters,
            partition_key=origin,
        )
    )

    # 5. Format results for the caller
    results = []

    for doc in documents:
        month_key = int(doc["month_key"])

        if carrier_code is None:
            # Return route totals plus all airlines
            results.append({
                "origin": doc["origin"],
                "dest": doc["dest"],
                "month_key": month_key,
                "totals": doc.get("totals", {}).copy(),
                "by_airline": [
                    airline.copy()
                    for airline in doc.get("by_airline", [])
                ],
            })

        else:
            # Return only the requested airline's statistics
            matching_airlines = [
                airline
                for airline in doc.get("by_airline", [])
                if str(airline.get("carrier_code", "")).upper()
                == carrier_code
            ]

            for airline in matching_airlines:
                results.append({
                    "origin": doc["origin"],
                    "dest": doc["dest"],
                    "month_key": month_key,
                    **airline,
                    "carrier_code": carrier_code,
                })

    return sorted(
        results,
        key=lambda record: record["month_key"],
    )


if __name__ == "__main__":
    stats = get_route_delay_stats(
        "ATL", "AUS", 202401, 202401
    )

    print("Records found:", len(stats))

    for record in stats:
        print("Route:", record["origin"], "->", record["dest"])
        print("Month:", record["month_key"])

        if "totals" in record:
            print("Flights:", record["totals"].get("flights"))
            print("Airlines:", len(record["by_airline"]))
        else:
            print("Airline:", record["carrier_code"])
            print("Flights:", record.get("flights"))
