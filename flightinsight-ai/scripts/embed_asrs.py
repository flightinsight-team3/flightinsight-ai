"""One-off: embed NASA ASRS reports with Ollama and upsert them into Cosmos asrs_reports.

Runs on a laptop (Ollama is local). Usage, once implemented:
    python scripts/embed_asrs.py path/to/asrs_export.csv

Notes:
- nomic-embed-text needs task prefixes: "search_document: " for reports,
  "search_query: " for questions at query time. Without them retrieval quality drops.
- Check Ollama's context length so long narratives are not silently truncated.
- quantizedFlat needs at least 1,000 vectors, so load at least 1,000 reports.
- Each document must match cosmos/schemas/asrs_report.schema.json.
"""

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


def main() -> None:
    raise NotImplementedError("embed_asrs")


if __name__ == "__main__":
    main()
