import csv
import os
import sys
from pathlib import Path

from azure.cosmos import CosmosClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))
from etl.transform_routes import build_route_documents, group_route_rows  # noqa: E402

# Step 1: Connect to Azure Cosmos DB
client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=os.environ["COSMOS_KEY"])

# Step 2: Select the existing database and container
database = client.get_database_client("flightinsight")
container = database.get_container_client("route_summaries")

# Step 3: Check the connection
container_info = container.read()

print("Connected to:", container_info["id"])

# Step 4: Check the source CSV file
csv_path = Path(__file__).parent / "route_airline_monthly_202401.csv"

print("CSV file exists:", csv_path.exists())

# Step 5: Transform CSV rows into route summary documents


rows = []

with open(csv_path, newline="", encoding="utf-8-sig") as file:
    reader = csv.DictReader(file)

    for row in reader:
        rows.append(
            {
                "route_key": int(row["route_key"]),
                "origin": row["origin"],
                "dest": row["dest"],
                "month_key": int(row["month_key"]),
                "carrier_code": row["carrier_code"],
                "flights": int(row["flights"]),
                "cancelled": int(row["cancelled"]),
                "diverted": int(row["diverted"]),
                "completed_flights": (
                    int(row["flights"]) - int(row["cancelled"]) - int(row["diverted"])
                ),
                "on_time_rate": float(row["on_time_rate"]) if row["on_time_rate"] else None,
                "avg_arr_delay_min": float(row["avg_arr_delay_min"])
                if row["avg_arr_delay_min"]
                else None,
                "p90_arr_delay_min": float(row["p90_arr_delay_min"])
                if row["p90_arr_delay_min"]
                else None,
                "weather_delay_share": float(row["weather_delay_share"])
                if row["weather_delay_share"]
                else None,
            }
        )

grouped = group_route_rows(rows)
documents = build_route_documents(grouped)

assert len(documents) == 828, "Unexpected document count!"
assert len({doc["id"] for doc in documents}) == len(documents), "Duplicate IDs!"
assert all(doc.get("origin") for doc in documents), "Missing origin partition key!"
assert all(doc.get("id") for doc in documents), "Missing document ID!"

print("SQL rows:", len(rows))
print("JSON documents ready:", len(documents))
print("First document ID:", documents[0]["id"])

# Step 6: Test uploading one document
test_document = documents[0]

print("Testing upload:", test_document["id"])

result = container.upsert_item(body=test_document)

print("Upload successful!")
print("Uploaded document ID:", result["id"])

# Step 7: Verify the uploaded document by reading it back
print("\nVerifying uploaded document...")

saved_document = container.read_item(
    item=test_document["id"], partition_key=test_document["origin"]
)

print("Read back document ID:", saved_document["id"])
print("Route:", saved_document["origin"], "->", saved_document["dest"])
print("Flights:", saved_document["totals"]["flights"])

# Compare the original document with the cloud document
for field in ["id", "route_key", "origin", "dest", "month_key", "totals", "by_airline"]:
    assert saved_document[field] == test_document[field], f"Mismatch in field: {field}"

print("Verification passed! Local JSON matches Cosmos DB!")

# Step 8: Prepare batch upload (dry run first)
print("\nPreparing batch upload...")

print("Total documents:", len(documents))
print("First document:", documents[0]["id"])
print("Last document:", documents[-1]["id"])

# Safety switch: False = preview only, True = upload
ENABLE_BATCH_UPLOAD = False

if ENABLE_BATCH_UPLOAD:
    success_count = 0
    failed_count = 0

    for index, document in enumerate(documents, start=1):
        try:
            container.upsert_item(body=document)
            success_count += 1

            if index % 50 == 0 or index == len(documents):
                print(f"Progress: {index}/{len(documents)}")

        except Exception as error:
            failed_count += 1
            print(f"Failed: {document['id']} - {error}")
            print("Batch upload stopped for safety.")
            raise

    print("\nBatch upload finished!")
    print("Successful:", success_count)
    print("Failed:", failed_count)

else:
    print("DRY RUN: No batch documents uploaded.")
    print("Set ENABLE_BATCH_UPLOAD = True when ready.")

# Step 9: Verify the number of documents in Cosmos DB
print("\nChecking document count in Cosmos DB...")

query = "SELECT VALUE COUNT(1) FROM c"

result = list(container.query_items(query=query, enable_cross_partition_query=True))

cloud_count = result[0]

print("Documents in Cosmos DB:", cloud_count)

assert cloud_count == len(documents), f"Expected {len(documents)} documents, found {cloud_count}"

print("Cloud document count verified!")
