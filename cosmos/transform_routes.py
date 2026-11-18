import csv
import json
from pathlib import Path
from collections import defaultdict


def group_route_rows(rows):
    # 按照 origin + dest + month_key 分组
    grouped = defaultdict(list)

    for row in rows:
        key = (
            row["origin"],
            row["dest"],
            row["month_key"]
        )

        grouped[key].append(row)

    return dict(grouped)


def build_route_documents(grouped):
    # 把同一条航线、同一个月份、不同航空公司的数据合并成一份 JSON 文档
    documents = []

    for (origin, dest, month_key), rows in grouped.items():
        total_flights = sum(row["flights"] for row in rows)
        total_cancelled = sum(row["cancelled"] for row in rows)
        total_diverted = sum(row["diverted"] for row in rows)

        document = {
            "id": f"{origin}-{dest}-{month_key}",
            "origin": origin,
            "dest": dest,
            "month_key": month_key,
            "totals": {
                "flights": total_flights,
                "cancelled": total_cancelled,
                "diverted": total_diverted
            },
            "by_airline": [
                {
                    "carrier_code": row["carrier_code"],
                    "flights": row["flights"]
                }
                for row in rows
            ]
        }

        documents.append(document)

    return documents


# Test using real SQL query results exported to CSV
if __name__ == "__main__":

    csv_path = Path(__file__).parent / "results.csv"

    sample_rows = []

    with open(csv_path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for row in reader:
            sample_rows.append({
                "origin": row["origin"],
                "dest": row["dest"],
                "month_key": int(row["month_key"]),
                "carrier_code": row["carrier_code"],
                "flights": int(row["flights"]),
                "cancelled": int(row["cancelled"]),
                "diverted": int(row["diverted"])
            })

    grouped = group_route_rows(sample_rows)
    documents = build_route_documents(grouped)

    print(json.dumps(documents, indent=2))



