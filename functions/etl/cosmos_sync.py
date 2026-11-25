# Azure SQL to Cosmos DB NoSQL synchronization.
from decimal import Decimal

from etl.common import setting, sql_connection
from etl.transform_routes import build_route_documents, group_route_rows


def get_cosmos_container():
    """Connect to the existing route_summaries container with the app's managed identity
    (or your `az login` locally, if your account has the Cosmos DB Built-in Data Contributor
    role — see infra/nosql.bicep `dataContributorPrincipalIds`)."""
    from azure.cosmos import CosmosClient
    from azure.identity import DefaultAzureCredential

    client = CosmosClient(setting("COSMOS_NOSQL_ENDPOINT"), credential=DefaultAzureCredential())
    database = client.get_database_client(setting("COSMOS_NOSQL_DATABASE"))

    return database.get_container_client("route_summaries")


def fetch_sql_rows(database: str = "prod"):
    # Read route-month aggregates from Azure SQL (prod flightinsight, or dev flightinsight-dev).

    query = """
        SELECT
            a.route_key,
            origin.iata_code AS origin,
            dest.iata_code AS dest,
            a.month_key,
            airline.carrier_code,
            a.flights,
            a.cancelled,
            a.diverted,
            a.on_time_rate,
            a.avg_arr_delay_min,
            a.p90_arr_delay_min,
            a.weather_delay_share
        FROM dbo.agg_route_monthly AS a
        JOIN dbo.dim_routes AS r
            ON a.route_key = r.route_key
        JOIN dbo.dim_airports AS origin
            ON r.origin_airport_key = origin.airport_key
        JOIN dbo.dim_airports AS dest
            ON r.dest_airport_key = dest.airport_key
        JOIN dbo.dim_airlines AS airline
            ON a.airline_key = airline.airline_key
    """

    with sql_connection(database) as connection:
        cursor = connection.cursor()
        cursor.execute(query)

        column_names = [column[0] for column in cursor.description]

        results = cursor.fetchall()

        rows = [dict(zip(column_names, row, strict=True)) for row in results]

    return rows


def prepare_rows_for_transform(sql_rows):
    # Convert SQL values into the format expected by the transformer."""

    prepared_rows = []

    for row in sql_rows:
        prepared_row = dict(row)

        for field in [
            "on_time_rate",
            "avg_arr_delay_min",
            "p90_arr_delay_min",
            "weather_delay_share",
        ]:
            value = prepared_row[field]

            if isinstance(value, Decimal):
                prepared_row[field] = float(value)

        prepared_row["completed_flights"] = (
            prepared_row["flights"] - prepared_row["cancelled"] - prepared_row["diverted"]
        )

        prepared_rows.append(prepared_row)

    return prepared_rows


def build_cosmos_documents(sql_rows):
    # Transform Azure SQL rows into Cosmos DB JSON documents."""

    prepared_rows = prepare_rows_for_transform(sql_rows)
    grouped = group_route_rows(prepared_rows)
    documents = build_route_documents(grouped)

    return documents


def sync_routes_to_cosmos(database: str = "prod"):
    # Synchronize route summaries from Azure SQL (prod or dev) to Cosmos DB.

    print(f"Fetching data from Azure SQL ({database})...")
    sql_rows = fetch_sql_rows(database)

    print("SQL rows fetched:", len(sql_rows))

    documents = build_cosmos_documents(sql_rows)

    print("JSON documents generated:", len(documents))

    if not documents:
        raise ValueError("No documents generated; refusing to sync.")

    container = get_cosmos_container()

    success = 0
    failed = 0

    for document in documents:
        try:
            container.upsert_item(body=document)
            success += 1
        except Exception as error:
            failed += 1
            print(f"Failed to sync {document['id']}: {error}")

    print(f"Sync complete! Success: {success}, Failed: {failed}")

    if failed:
        raise RuntimeError(f"Cosmos sync failed for {failed} documents")

    return {
        "sql_rows": len(sql_rows),
        "documents_synced": success,
        "documents_failed": failed,
    }
