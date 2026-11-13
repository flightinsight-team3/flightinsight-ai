# scripts/

One-off or manual scripts that are not part of the scheduled pipeline.

| Script | Purpose |
|---|---|
| `embed_asrs.py` | Embed ASRS reports with local Ollama and upsert into Cosmos `asrs_reports` |

Read settings from `.env` (see `.env.example`). Never hard-code keys.
