# AI & Vector Search: progress report

As of 2026-11-18 · Owner: Jing Chen (AI & Vector Search, integration lead)

The ASRS safety-report pipeline and the chat agent now work end to end:
1,291 NASA ASRS reports are embedded in Cosmos DB, a LangChain agent answers questions with
two tools, and a Streamlit UI runs locally. The work is on branch `jchen-asrs-embeddings`.
Which questions the assistant can answer today, and who needs to do what for the rest, is in
[AI assistant: capability status](#ai-assistant-capability-status) at the end.

Scope of this module:

- **P3:** prepare the ASRS dataset, the Ollama embedding environment, and Cosmos DB vector search.
- **P4:** ASRS semantic search, the LangChain agent with a Streamlit UI, and overall integration.

## Why three months of ASRS data (January–March 2024)

We load ASRS reports for January to March 2024. One month is not enough; a full year is more
than we need right now.

1. **The vector index needs at least 1,000 vectors.** The Cosmos `quantizedFlat` index on
   `narrative_vector` requires 1,000 or more vectors. January 2024 alone has 412 reports;
   January to March has 1,291.
2. **It covers the flight data month.** Flight and route statistics use January 2024
   (202401). ASRS reports can only be matched to flight statistics by month (and, where
   present, airport), so the ASRS data must include January.
3. **It matches the period in the P2 design document's demo question** (January to March 2024).
4. **It is cheap to build.** Embedding takes about 0.6 seconds per report on a laptop CPU, so
   1,291 reports took about 13 minutes. A full year would take several times longer and use
   more Cosmos throughput (the container has 400 RU/s).

The data set is reproducible: `scripts/download_asrs.py --start 2024-01 --end 2024-03`
downloads the same 1,291 reports. More months can be added later without reloading, because
`scripts/embed_asrs.py <export.csv> --skip-existing` skips reports already in Cosmos.

## Completed modules

All 10 modules are done. 114 unit tests pass and `ruff check` passes.

| Module | File | What it does | Verified by |
| --- | --- | --- | --- |
| ASRS download | `scripts/download_asrs.py` → `data/asrs_2024Q1.csv` (CSV not in git) | Downloads January–March 2024 reports from ASRS Database Online | Re-download gives the same 1,291 reports |
| ASRS parsing | `app/asrs/parse.py` | CSV → Cosmos documents: airport, aircraft family, flight phase, reporter, anomaly, narrative | Unit tests + JSON schema validation |
| Embeddings | `app/asrs/embeddings.py` | Ollama + `nomic-embed-text`, 768 dimensions | Unit tests + real run |
| Embedding loader | `scripts/embed_asrs.py` | Embeds reports in batches and writes them to Cosmos `asrs_reports`; can resume | All 1,291 reports loaded |
| Safety report search | `app/tools/safety_search.py` | `search_safety_reports`: semantic search with month, airport and aircraft filters | Real queries, about 0.1 s each |
| Route delay stats | `app/tools/route_stats.py` | `get_route_delay_stats`: reads Cosmos `route_summaries`; same signature as `cosmos/route_queries.py` | Numbers match the Cosmos documents |
| LLM selection | `app/agent/llm.py` | Switches between Gemini and a local Ollama model; falls back to Gemini Flash-Lite when Gemini is overloaded | Unit tests + real run |
| Agent | `app/agent/agent.py` | LangGraph agent with both tools; cites report ACNs, uses only tool data, answers in the user's language | Unit tests + real questions in English and Chinese |
| Streamlit UI | `app/ui/streamlit_app.py` | Chat UI; each answer shows its tool calls, arguments, results and time | Run locally |
| LLM comparison | `scripts/compare_llms.py` | Asks each model the same questions and writes a comparison table | One full run |

Cosmos access uses each person's Entra ID login (`az login`) with the Cosmos DB Built-in Data
Contributor role, so no account key is needed. App dependencies are in `requirements-app.txt`;
see also `app/README.md`, `scripts/README.md` and `.env.example`.

## Data status

ASRS data covers January–March 2024; route delay data covers January 2024.

| Data | Location | Count | Coverage | Limitations |
| --- | --- | --- | --- | --- |
| ASRS safety reports | Cosmos `asrs_reports` | 1,291 (202401: 412, 202402: 377, 202403: 498, other: 4) | January–March 2024 | Only 203 reports name an airport; ASRS replaces the rest with "ZZZ" to protect reporters. 550 have a known aircraft family. |
| Route delay statistics | Cosmos `route_summaries` | 828 routes | January 2024 (202401), between the 30 busiest US airports | `best_departure_hours`, `delay_causes_min` and `p90_arr_delay_min` are empty in all documents |

Missing airports are part of ASRS's de-identification and cannot be recovered. The agent is
told to search again without the airport filter when a filtered search returns fewer than
3 reports, and to say so in its answer.

## LLM comparison

We recommend Gemini as the main model and the local Ollama model as a fallback. On the same
6 questions, Gemini took 23.5 seconds per question on average with every number correct;
qwen2.5:7b took 177.6 seconds and got one answer wrong.

| Measure | Gemini 3.6 Flash (cloud) | qwen2.5:7b (local Ollama) |
| --- | --- | --- |
| Mean time per question (s) | 23.5 | 177.6 |
| Called the right tools | 6/6 | 6/6 |
| Correct numbers | 6/6, checked against Cosmos | 5/6: called AA's 13.67 min the lowest DFW→LAX delay; DL's 1.86 min was lowest |
| Reliability | Returns 503 when Google's servers are busy; the agent then falls back to Flash-Lite | No network needed, but slow on a laptop CPU |
| Cost | Free tier (quota per Google Cloud project) | Free |

Tested on an Intel Core i7 laptop with 16 GB RAM and no GPU. `gemini-3.8-flash` kept timing
out on the test day, so the default is `gemini-3.6-flash` (set with `GEMINI_MODEL`).
Embeddings stay on Ollama + `nomic-embed-text` whichever chat model is used, because queries
must be embedded with the same model as the reports.

## Remaining work

Four items remain on this module; one waits on the graph database.

**This module**

- [x] Open a draft pull request for `jchen-asrs-embeddings` (#24)
- [ ] Merge with `jingyangwang-cosmos-db`: keep one implementation of `get_route_delay_stats`
- [ ] Wire the route-network graph queries (from the Cosmos multi-model module) into the agent as a tool once the graph is loaded
- [ ] Confirm the final LLM and write up the comparison in the P4 report
- [ ] Prepare the demo: pick the questions and record it

**Depends on other modules**

| Item | Effect on this module | Who |
| --- | --- | --- |
| Load the Gremlin `route_network` graph (`graph.py` is not implemented yet) and provide the query functions | Route-network questions cannot be answered | Jing Yang Wang |
| Fill `best_departure_hours` and `delay_causes_min` in `route_summaries` | "Best departure time" and delay-cause questions cannot be answered | Jing Yang Wang or Chi Zhang (owner not confirmed) |
| Flight-level and flight-weather query functions in Azure SQL | Flight lookup and weather-delay questions cannot be answered | Chi Zhang, Jinkun Zhao |
| Install `requirements-app.txt` in CI | Agent tests are skipped in CI (they need LangChain) | Jinkun Zhao |

**Open questions for the team**

- Who owns the Power BI dashboards?
- ADF has no master pipeline and no scheduled runs yet; the P2/P3 plans name Airflow, which
  ADF replaced. The report should explain the change.
- There is no source for holiday data yet.
- What should the route-network query functions return? Agree on the format before wiring them in.

## How to run

From the repository root. `.env` needs `COSMOS_NOSQL_ENDPOINT`, `GOOGLE_API_KEY` and
`GEMINI_MODEL` (see `.env.example`).

```bash
pip install -r requirements-dev.txt -r functions/requirements.txt -r requirements-app.txt
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
az login
streamlit run app/ui/streamlit_app.py
```

Other commands:

- Download ASRS reports: `python scripts/download_asrs.py --start 2024-01 --end 2024-03 --out data/asrs_2024Q1.csv`
- Run the tests: `pytest -q`
- Compare the models again: `python scripts/compare_llms.py`
- Load a new ASRS export: `python scripts/embed_asrs.py <export.csv> --skip-existing`

## AI assistant: capability status

The assistant can fully answer safety-report questions today and partly answer route
performance questions; the other question types wait on tools or data from other modules.
Flight and route questions use January 2024 data. Each row is one example question the final
demo should handle.

**Status:** Works = answered correctly in tests on real data · Partial = works with limits ·
Not built = no tool yet.

| # | Feature | Example question | Tool | Status | What is missing | Who needs to do what |
| --- | --- | --- | --- | --- | --- | --- |
| 1a | Route performance | "How on time were Seattle to New York flights in January 2024?" | `get_route_delay_stats` | Partial | "New York" is JFK, LGA and EWR; the tool takes one destination per call, so the agent must query each airport and combine them. | Jing Chen: let the tool or agent query JFK, LGA and EWR and combine the results |
| 1b | Route performance | "What departure time is most on time from Seattle to New York?" | `get_route_delay_stats` | Not built | `best_departure_hours` is in the schema but empty in all 828 route documents. | Jing Yang Wang or Chi Zhang (owner not confirmed): compute `best_departure_hours` in the SQL route view and fill it in `route_summaries` |
| 2a | Delay statistics | "Which airline had the most delays in January?" | `get_delay_breakdown` | Not built | Can be computed from the per-airline stats in `route_summaries`; tool not written. | Jing Chen: write `get_delay_breakdown` that ranks airlines from `route_summaries` |
| 2b | Delay statistics | "How much longer are delays on snowy days?" | `get_delay_breakdown` | Not built | Needs flights matched to weather (`fact_flight_weather` in Azure SQL) and a query function. | Jinkun Zhao: finish flight-weather matching into `fact_flight_weather`. Chi Zhang: provide a SQL query function for delays by weather condition |
| 2c | Delay statistics | "Which airport is the worst for delays?" | `get_delay_breakdown` | Not built | Can be computed from `route_summaries`; tool not written. `delay_causes_min` is empty, so delay causes cannot be shown. | Jing Chen: add airport ranking to `get_delay_breakdown`. Jing Yang Wang or Chi Zhang (owner not confirmed): fill `delay_causes_min` in `route_summaries` |
| 3 | Flight lookup | "Was AS 12 late on January 15?" | `lookup_flight` | Not built | Needs flight-level data (`fact_flights` in Azure SQL) and a query function. Both SQL databases are paused; whether they hold data and how the app connects is not confirmed. | Chi Zhang: confirm `fact_flights` has January 2024 data, provide a lookup function by airline, flight number and date, and say how the app connects to Azure SQL |
| 4a | Route network | "Where can I fly nonstop from Denver?" | `query_route_network` | Not built | Gremlin graph `route_network` is not loaded yet; no query function. | Jing Yang Wang: load the `route_network` graph and provide a nonstop-destinations query function |
| 4b | Route network | "Which airports are the biggest hubs?" | `query_route_network` | Not built | Same as 4a. | Jing Yang Wang: provide a hub query function (airports ranked by number of routes) |
| 4c | Route network | "How do I connect from Seattle to Miami?" | `query_route_network` | Not built | Same as 4a; alternative-route search is a planned graph query. | Jing Yang Wang: provide the alternative-route (connection) query function |
| 5 | Safety reports | "What risks do crews report when flights are delayed?" | `search_safety_reports` | Works | 1,291 ASRS reports (January–March 2024) with vectors. Airport filters match few reports because ASRS removes most airport names. | — |
| 6 | Combined question | "Was Seattle to New York on time in January, and is there a better connection?" | several tools in one answer | Partial | The agent already chains tools (tested: route stats + safety reports in one answer). Needs rows 1a and 4c. | Jing Chen: finish 1a and wire in the graph tools. Jing Yang Wang: the 4c query function |
| 7 | City name → airport code | "Seattle" → `SEA` | LLM + prompt | Partial | The LLM converts names correctly in tests, but the 30 supported airports are not listed in the prompt and multi-airport cities are not handled. | Jing Chen: list the 30 supported airports with their cities in the agent prompt |
| 8 | Time expressions | "January", "winter", "January to March" → `month_key` range | LLM + prompt | Works | "January to March" became 202401–202403 in tests. | — |
| 9 | Answers only from data | Every number comes from a tool result | Prompt rules | Works | Gemini: 6/6 answers with correct numbers. Local qwen2.5:7b: 5/6. | — |
| 10 | Explain out-of-scope questions | "On-time rate in July 2024?", "Tomorrow's flights?", "Ticket prices?" | Prompt rules | Works | Tested with July 2024: the answer says only January is available instead of guessing. | — |
| 11 | Show evidence | Tool calls and cited reports shown in the UI | Streamlit UI | Partial | Each answer expands to show tool calls, arguments and raw results. Cited reports are raw JSON, not readable cards. | Jing Chen: show cited reports as cards (ACN, date, synopsis) in the UI |
| 12 | Follow-up questions | "What about Delta?" after a route question | Agent history | Partial | Conversation history is passed to the model and covered by unit tests; not yet tested with a real model. | Jing Chen: test follow-up questions with Gemini and fix what fails |

### Summary

| Status | Rows |
| --- | --- |
| Works | 5, 8, 9, 10 |
| Partial | 1a, 6, 7, 11, 12 |
| Not built | 1b, 2a, 2b, 2c, 3, 4a, 4b, 4c |

Next steps that do not wait on others: `get_delay_breakdown` for airlines and airports
(2a, 2c), the airport list and multi-airport cities in the prompt (1a, 7), report cards in the
UI (11), and a real follow-up-question test (12).
