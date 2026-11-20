# scripts/

One-off or manual scripts that are not part of the scheduled pipeline.

| Script | Purpose |
|---|---|
| `download_asrs.py` | Download ASRS reports for a range of months as CSV |
| `embed_asrs.py` | Embed ASRS reports with local Ollama and upsert into Cosmos `asrs_reports` |
| `compare_llms.py` | Ask Gemini and the local Ollama model the same questions; write a comparison table |

Read settings from `.env` (see `.env.example`). Never hard-code keys.

## download_asrs.py

[ASRS Database Online](https://asrs.arc.nasa.gov/search/database.html) has no API, so the script
replays its query wizard: filter by Date of Incident, run the search, export CSV. Our data set:

```bash
python scripts/download_asrs.py --start 2024-01 --end 2024-03 --out data/asrs_2024Q1.csv
```

It prints how many reports matched. The wizard exports at most 10,000 reports per query, so
split longer ranges. If NASA changes the wizard, the error names the failing step; the same
export can be made by hand in the browser (Date of Incident filter → Search → Export → CSV).

## embed_asrs.py

1. Download the reports (above), at least 1,000 of them: quantizedFlat needs 1,000 vectors.
   Keep the CSV under `data/` (git-ignored).
2. Install [Ollama](https://ollama.com) and run `ollama pull nomic-embed-text`.
3. Set `COSMOS_NOSQL_ENDPOINT` in `.env` and run `az login` (your account needs the Cosmos DB
   Built-in Data Contributor role). Alternatively set `COSMOS_NOSQL_KEY`.

```bash
python scripts/embed_asrs.py data/asrs_2024Q1.csv --parse-only   # check the export
python scripts/embed_asrs.py data/asrs_2024Q1.csv --dry-run --limit 20   # test Ollama
python scripts/embed_asrs.py data/asrs_2024Q1.csv                # embed and upsert
python scripts/embed_asrs.py data/asrs_2024Q1.csv --skip-existing   # resume after a failure
```
