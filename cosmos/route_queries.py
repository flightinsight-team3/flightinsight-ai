import os
from azure.cosmos import CosmosClient


def get_route_delay_stats(origin, dest, start_month, end_month):
    """
    Query real route delay statistics from Azure Cosmos DB.

    Returns a list of route summary documents,
    sorted by month.
    """

    # Step 1: Connect to Azure Cosmos DB
    client = CosmosClient(
        os.environ["COSMOS_ENDPOINT"],
        credential=os.environ["COSMOS_KEY"]
    )

    # Step 2: Select the database and container
    database = client.get_database_client("flightinsight")
    container = database.get_container_client("route_summaries")

    # Step 3: Normalize input values
    origin = origin.strip().upper()
    dest = dest.strip().upper()
    start_month = int(start_month)
    end_month = int(end_month)

    if start_month > end_month:
        raise ValueError("start_month cannot be after end_month")

    # Step 4: Query Cosmos DB
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
        {"name": "@end_month", "value": end_month}
    ]

    results = list(
        container.query_items(
            query=query,
            parameters=parameters,
            partition_key=origin
        )
    )

    # Step 5: Sort by month
    return sorted(results, key=lambda doc: int(doc["month_key"]))


if __name__ == "__main__":
    # Step 6: Test the function
    stats = get_route_delay_stats("ATL", "AUS", 202401, 202401)

    print("Documents found:", len(stats))

    for doc in stats:
        print("Route:", doc["origin"], "->", doc["dest"])
        print("Month:", doc["month_key"])
        print("Flights:", doc["totals"]["flights"])
        print("On-time rate:", doc["totals"]["on_time_rate"])
        print("Average arrival delay:", doc["totals"]["avg_arr_delay_min"])
