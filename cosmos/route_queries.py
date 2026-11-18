import json
from pathlib import Path


def get_route_delay_stats(origin, dest, start_month, end_month):

    # Load all route summary sample JSON files.
    samples_dir = Path(__file__).parent / "samples"

    documents = []

    for sample_path in samples_dir.glob("route_summary*.sample.json"):
        with open(sample_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            documents.append(data)


    matches = [
        doc
        for doc in documents
        if doc["origin"] == origin.upper()
        and doc["dest"] == dest.upper()
        and start_month <= int(doc["month_key"]) <= end_month
    ]

    return sorted(matches, key=lambda doc: int(doc["month_key"]))
