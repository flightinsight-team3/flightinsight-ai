"""One-off: embed NASA ASRS reports with Ollama and upsert them into Cosmos asrs_reports.

Runs on a laptop (Ollama is local). Settings come from .env (see .env.example).

    python scripts/embed_asrs.py data/asrs_2024.csv --parse-only   # check the export, no Ollama
    python scripts/embed_asrs.py data/asrs_2024.csv --dry-run      # parse + embed, no Cosmos
    python scripts/embed_asrs.py data/asrs_2024.csv                # parse + embed + upsert

Re-running is safe: documents are upserted by ACN, and --skip-existing skips reports that are
already in Cosmos. quantizedFlat needs at least 1,000 vectors, so load at least 1,000 reports.
Every document matches cosmos/schemas/asrs_report.schema.json; the task prefixes and Ollama's
context length are handled in app/asrs/embeddings.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.asrs.parse import ParseResult, embedding_text, parse_export  # noqa: E402

MIN_VECTORS = 1000


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from app.settings import load_dotenv

    load_dotenv()
    result = parse_export(args.csv)
    print_summary(result)
    documents = result.documents[: args.limit] if args.limit else result.documents
    if args.parse_only:
        if documents:
            print("\nFirst document:\n" + preview(documents[0]))
        return 0

    from app.asrs.embeddings import OllamaEmbedder

    container = None
    if not args.dry_run:
        from app.asrs.store import asrs_container, existing_ids

        container = asrs_container()
        if args.skip_existing:
            done = existing_ids(container)
            documents = [d for d in documents if d["id"] not in done]
            print(f"Skipping {len(done)} reports already in Cosmos; {len(documents)} to go")

    written = run(documents, OllamaEmbedder(), container, args.batch_size)
    if args.dry_run:
        if documents:
            print("\nFirst document (dry run, nothing written):\n" + preview(documents[0]))
    else:
        print(f"\nUpserted {written} documents into asrs_reports")
    return 0


def run(documents: list[dict], embedder, container, batch_size: int = 16) -> int:
    """Embed documents in batches (adds narrative_vector in place); upsert if container is set."""
    written = 0
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]
        vectors = embedder.embed([embedding_text(doc) for doc in batch])
        for doc, vector in zip(batch, vectors, strict=True):
            doc["narrative_vector"] = vector
            if container is not None:
                container.upsert_item(doc)
                written += 1
        print(f"  embedded {start + len(batch)}/{len(documents)}", flush=True)
    return written


def print_summary(result: ParseResult) -> None:
    docs = result.documents
    print(f"Parsed {len(docs)} reports; rejected {sum(result.rejected.values())}")
    for reason, count in result.rejected.most_common():
        print(f"  rejected {reason}: {count}")
    if not docs:
        return
    months = Counter(d["month_key"] for d in docs)
    airports = Counter(d["airport_code"] for d in docs if d["airport_code"])
    families = Counter(d["aircraft_family"] for d in docs if d["aircraft_family"])
    print(f"Months: {', '.join(f'{m} ({n})' for m, n in sorted(months.items()))}")
    print(f"With airport: {sum(airports.values())}; top: {top(airports)}")
    print(f"With aircraft family: {sum(families.values())}; top: {top(families)}")
    if len(docs) < MIN_VECTORS:
        print(f"Note: the quantizedFlat index needs at least {MIN_VECTORS} reports")


def top(counter: Counter, n: int = 5) -> str:
    return ", ".join(f"{k} ({v})" for k, v in counter.most_common(n)) or "-"


def preview(doc: dict) -> str:
    shown = dict(doc)
    shown["narrative"] = shorten(shown["narrative"])
    shown["synopsis"] = shorten(shown["synopsis"])
    if "narrative_vector" in shown:
        vector = shown["narrative_vector"]
        shown["narrative_vector"] = [*vector[:5], f"... {len(vector)} values"]
    return json.dumps(shown, indent=2, ensure_ascii=False)


def shorten(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path, help="ASRS Database Online CSV export")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--parse-only", action="store_true", help="only parse and summarize")
    mode.add_argument("--dry-run", action="store_true", help="parse and embed, don't write")
    parser.add_argument("--skip-existing", action="store_true", help="skip IDs already in Cosmos")
    parser.add_argument("--limit", type=int, help="only process the first N reports")
    parser.add_argument("--batch-size", type=int, default=16, help="texts per Ollama call")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
