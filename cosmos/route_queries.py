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
    Query route-month statistics from Azure Cosmos DB NoSQL.

    Each document represents one route x month.
    Airline-level statistics are nested in by_airline.

    Returns a list of documents sorted by month.
    """

    # Step 1: Normalize and validate inputs
    origin = origin.strip().upper()
    dest = dest.strip().upper()
    start_month = int(start_month)
    end_month = int(end_month)

    for airport in (origin, dest):
        if (
            len(airport) != 3
            or not airport.isascii()
            or not airport.isalpha()
        ):
            raise ValueError("Airport codes must be 3 letters")

    for month_key in (start_month, end_month):
        year, month = divmod(month_key, 100)
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError("Invalid month_key")

    if start_month > end_month:
        raise ValueError("start_month cannot be after end_month")

    if carrier_code is not None:
        carrier_code = carrier_code.strip().upper()
        if not carrier_code:
            raise ValueError("carrier_code cannot be empty")

    # Step 2: Connect to Cosmos DB
    client = CosmosClient(
        os.environ["COSMOS_ENDPOINT"],
        credential=os.environ["COSMOS_KEY"],
    )

    database = client.get_database_client("flightinsight")
    container = database.get_container_client("route_summaries")

    # Step 3: Query route-month documents
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

    results = list(
        container.query_items(
            query=query,
            parameters=parameters,
            partition_key=origin,
        )
    )

    # Step 4: Optionally filter airline details
    if carrier_code is not None:
        for doc in results:
            doc["by_airline"] = [
                airline
                for airline in doc.get("by_airline", [])
                if airline["carrier_code"].upper() == carrier_code
            ]

    # Step 5: Sort by month
    return sorted(
        results,
        key=lambda doc: int(doc["month_key"]),
    )


if __name__ == "__main__":
    stats = get_route_delay_stats(
        "ATL", "AUS", 202401, 202401
    )

    print("Documents found:", len(stats))

    for doc in stats:
        print("Route:", doc["origin"], "->", doc["dest"])
        print("Month:", doc["month_key"])
        print("Flights:", doc["totals"]["flights"])
        print("Airlines:", len(doc["by_airline"]))