import os
from decimal import Decimal

import pyodbc
from azure.cosmos import CosmosClient
from transform_routes import build_route_documents, group_route_rows


def fetch_sql_rows():
    # Read the latest route-month aggregates from Azure SQL.

    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER=tcp:{os.environ['AZURE_SQL_SERVER']},1433;"
        f"DATABASE={os.environ['AZURE_SQL_DATABASE']};"
        f"UID={os.environ['AZURE_SQL_USER']};"
        f"PWD={os.environ['AZURE_SQL_PASSWORD']};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=60;"
    )

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

    with pyodbc.connect(connection_string) as connection:
        cursor = connection.cursor()
        cursor.execute(query)

        column_names = [column[0] for column in cursor.description]

        results = cursor.fetchall()

        rows = [dict(zip(column_names, row, strict=True)) for row in results]

        return rows


def prepare_rows_for_transform(sql_rows):
    # Convert SQL rows into the format expected by transform_routes.py.

    prepared_rows = []

    for row in sql_rows:
        prepared_row = dict(row)

        # Convert SQL Decimal values to Python float
        for field in [
            "on_time_rate",
            "avg_arr_delay_min",
            "p90_arr_delay_min",
            "weather_delay_share",
        ]:
            value = prepared_row[field]

            if isinstance(value, Decimal):
                prepared_row[field] = float(value)

        # Calculate completed flights
        prepared_row["completed_flights"] = (
            prepared_row["flights"] - prepared_row["cancelled"] - prepared_row["diverted"]
        )

        prepared_rows.append(prepared_row)

    return prepared_rows


def upsert_route_documents(container, documents, dry_run=True):
    # Insert or update route documents in Cosmos DB.

    if dry_run:
        print(f"DRY RUN: {len(documents)} documents ready.")
        print("No documents uploaded.")
        return

    success = 0
    failed = 0

    for document in documents:
        try:
            container.upsert_item(body=document)
            success += 1
        except Exception as error:
            failed += 1
            print(f"Failed to upload {document['id']}: {error}")

    print(f"Upload complete! Success: {success}, Failed: {failed}")


# test
if __name__ == "__main__":
    print("Connecting to Azure SQL...")
    sql_rows = fetch_sql_rows()

    print("Connected successfully!")
    print("SQL rows fetched:", len(sql_rows))

    prepared_rows = prepare_rows_for_transform(sql_rows)

    grouped = group_route_rows(prepared_rows)
    documents = build_route_documents(grouped)

    print("JSON documents generated:", len(documents))

    assert len(documents) == len({doc["id"] for doc in documents})
    assert all(doc.get("origin") for doc in documents)

    if documents:
        print("First document ID:", documents[0]["id"])
        print("First document totals:", documents[0]["totals"])

    print("SQL → JSON transformation successful!")

    print("\nConnecting to Cosmos DB...")

    cosmos_client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=os.environ["COSMOS_KEY"])

    database = cosmos_client.get_database_client("flightinsight")
    container = database.get_container_client("route_summaries")

    container_info = container.read()
    print("Connected to Cosmos container:", container_info["id"])

    print("Cosmos partition key:", container_info["partitionKey"]["paths"])
    print("First JSON document origin:", documents[0]["origin"])
    print("First JSON document ID:", documents[0]["id"])

    cloud_count = list(
        container.query_items(
            query="SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
        )
    )[0]

    print("Existing Cosmos documents:", cloud_count)
    print("New JSON documents ready:", len(documents))

    # Safety switch: True = preview only, False = upload
    DRY_RUN = True

    upsert_route_documents(container=container, documents=documents, dry_run=DRY_RUN)

    if not DRY_RUN:
        first_doc = documents[0]

        saved_doc = container.read_item(item=first_doc["id"], partition_key=first_doc["origin"])

        print("Verified document ID:", saved_doc["id"])
        print("Verified flights:", saved_doc["totals"]["flights"])
        print("Verified on-time rate:", saved_doc["totals"]["on_time_rate"])
