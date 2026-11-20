# app/

LangChain agent (`agent/`) and Streamlit chat UI (`ui/`), plus the three chatbot tools.

Status, data coverage and the LLM comparison: [docs/ai-vector-search-progress.md](../docs/ai-vector-search-progress.md).

## Run the chat

```bash
pip install -r requirements-dev.txt -r functions/requirements.txt -r requirements-app.txt
ollama pull nomic-embed-text      # embeddings (always needed)
ollama pull qwen2.5:7b            # only for the local chat model
az login                          # Cosmos access (or set COSMOS_NOSQL_KEY)
streamlit run app/ui/streamlit_app.py
```

`.env` needs `COSMOS_NOSQL_ENDPOINT`, and for Gemini `GOOGLE_API_KEY` and `GEMINI_MODEL`
(see `.env.example`). The sidebar switches between Gemini and the local Ollama model; each answer
shows the tool calls, their arguments and results, and the time taken.

From Python:

```python
from app.agent.agent import ask, build_agent

answer = ask(build_agent("gemini"), "How on time was ATL to ORD in January 2024?")
answer.text, answer.tool_calls, answer.seconds
```

`scripts/compare_llms.py` asks both models the same questions and writes a markdown table
(time, whether the right tools were called, answers) to `data/llm_comparison.md`.

| Tool | File | Data source | Status |
|---|---|---|---|
| `search_safety_reports(query, filters, top_k)` | `tools/safety_search.py` | Cosmos `asrs_reports` vector search | Done |
| `get_route_delay_stats(origin, dest, start_month, end_month)` | `tools/route_stats.py` | Cosmos `route_summaries` | Done (same signature as `cosmos/route_queries.py`) |
| `find_alternative_routes(origin, dest)` | — | Cosmos Gremlin `route_network` | Waiting on graph queries |

`asrs/` holds the ASRS pieces shared by the search tool and `scripts/embed_asrs.py`:
CSV parsing (`parse.py`), Ollama embeddings (`embeddings.py`) and the Cosmos container (`store.py`).

## search_safety_reports

```python
from app.tools.safety_search import search_safety_reports

search_safety_reports(
    "What risks do crews report when rushed by delays?",
    filters={"start_month": 202401, "end_month": 202403, "airport_code": "ORD"},
    top_k=5,
)
```

Filters (all optional): `month_key`, `start_month`, `end_month`, `airport_code`, `aircraft_family`
(`B737`, `A320`, `CRJ`, `ERJ`, `DHC8`, `MD80`). Unknown filter names raise `ValueError`.
Each result has the report fields plus `similarity` (cosine; higher is more similar).
The question is embedded with the same Ollama model as the reports, so Ollama must be running.
