import csv
import json
from collections import defaultdict
from pathlib import Path


def group_route_rows(rows):
    # Input grain: route × airline × month (one SQL row per combination)
    # Group by origin, destination, and month_key
    # Output: (origin, dest, month_key) -> list of airline-level rows
    grouped = defaultdict(list)

    for row in rows:
        key = (row["origin"], row["dest"], row["month_key"])

        grouped[key].append(row)

    return dict(grouped)


def build_route_documents(grouped):
    # Create one document for each route and month.
    # Combine flight counts, cancellations, and diversions from all airlines.
    # Keep each airline's flight count separately in the by_airline list.
    documents = []

    for (origin, dest, month_key), rows in grouped.items():
        total_flights = sum(row["flights"] for row in rows)
        total_cancelled = sum(row["cancelled"] for row in rows)
        total_diverted = sum(row["diverted"] for row in rows)
        total_completed = sum(row["completed_flights"] for row in rows)

        def weighted_average(field, rows=rows):
            valid_rows = [
                row for row in rows if row[field] is not None and row["completed_flights"] > 0
            ]

            total_weight = sum(row["completed_flights"] for row in valid_rows)

            if total_weight == 0:
                return None

            result = sum(row[field] * row["completed_flights"] for row in valid_rows) / total_weight

            return round(result, 4)

        document = {
            "id": f"{origin}-{dest}-{month_key}",
            "route_key": rows[0]["route_key"],
            "origin": origin,
            "dest": dest,
            "month_key": month_key,
            "totals": {
                "flights": total_flights,
                "cancelled": total_cancelled,
                "diverted": total_diverted,
                "completed_flights": total_completed,
                "on_time_rate": weighted_average("on_time_rate"),
                "avg_arr_delay_min": weighted_average("avg_arr_delay_min"),
                "cancel_rate": round(total_cancelled / total_flights, 4) if total_flights else None,
                "divert_rate": round(total_diverted / total_flights, 4) if total_flights else None,
            },
            "by_airline": [
                {
                    "carrier_code": row["carrier_code"],
                    "flights": row["flights"],
                    "cancelled": row["cancelled"],
                    "diverted": row["diverted"],
                    "completed_flights": row["completed_flights"],
                    "on_time_rate": row["on_time_rate"],
                    "avg_arr_delay_min": row["avg_arr_delay_min"],
                    "p90_arr_delay_min": row["p90_arr_delay_min"],
                    "weather_delay_share": row["weather_delay_share"],
                }
                for row in rows
            ],
        }

        documents.append(document)

    return documents


# Test using real SQL query results exported to CSV
if __name__ == "__main__":
    csv_path = Path(__file__).parent / "route_airline_monthly_202401.csv"

    sample_rows = []

    with open(csv_path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            sample_rows.append(
                {
                    "route_key": int(row["route_key"]),
                    "origin": row["origin"],
                    "dest": row["dest"],
                    "month_key": int(row["month_key"]),
                    "carrier_code": row["carrier_code"],
                    "flights": int(row["flights"]),
                    "cancelled": int(row["cancelled"]),
                    "diverted": int(row["diverted"]),
                    "completed_flights": int(row["completed_flights"]),
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

    grouped = group_route_rows(sample_rows)
    documents = build_route_documents(grouped)

    # Validate the number of SQL rows and generated documents
    print("SQL rows:", len(sample_rows))
    print("JSON documents:", len(documents))

    # Compare totals before and after transformation
    sql_flights = sum(row["flights"] for row in sample_rows)
    sql_cancelled = sum(row["cancelled"] for row in sample_rows)
    sql_diverted = sum(row["diverted"] for row in sample_rows)
    sql_completed = sum(row["completed_flights"] for row in sample_rows)

    json_flights = sum(doc["totals"]["flights"] for doc in documents)
    json_cancelled = sum(doc["totals"]["cancelled"] for doc in documents)
    json_diverted = sum(doc["totals"]["diverted"] for doc in documents)
    json_completed = sum(doc["totals"]["completed_flights"] for doc in documents)

    print("SQL total flights:", sql_flights)
    print("JSON total flights:", json_flights)
    print("SQL total cancelled:", sql_cancelled)
    print("JSON total cancelled:", json_cancelled)
    print("SQL total diverted:", sql_diverted)
    print("JSON total diverted:", json_diverted)

    assert sql_flights == json_flights, "Flight totals do not match!"
    assert sql_cancelled == json_cancelled, "Cancellation totals do not match!"
    assert sql_diverted == json_diverted, "Diversion totals do not match!"

    assert sql_completed == json_completed, "Completed totals do not match!"

    # Ensure each document has a unique ID
    document_ids = [doc["id"] for doc in documents]
    assert len(document_ids) == len(set(document_ids)), "Duplicate document IDs!"

    print("SQL total completed:", sql_completed)
    print("JSON total completed:", json_completed)
    print("Document IDs are unique!")

    print("Batch validation passed!")

    # Display the first generated document
    print(json.dumps(documents[0], indent=2))

    # Save one real document for a safe Cosmos DB upload test
    output_path = Path(__file__).parent / "test_route_document.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(documents[0], file, indent=2)

    print("Test document saved:", output_path)
