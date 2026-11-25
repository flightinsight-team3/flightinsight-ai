# functions/

Python Azure Functions app (Flex Consumption). ADF calls these HTTP endpoints in order.

| Endpoint | Module | Step |
|---|---|---|
| `POST /api/bts/ingest` | `etl/bts.py` | Download, clean, UTC, validate → Data Lake |
| `POST /api/airports/ingest` | `etl/airports.py` | Same for airport/geography reference data |
| `POST /api/noaa/ingest` | `etl/noaa.py` | Same for weather |
| `POST /api/graph/load` | `etl/graph.py` | `agg_route_monthly` → Gremlin graph |
| `POST /api/cosmos/sync` | `etl/cosmos_sync.py` | Azure SQL route summaries → Cosmos DB |

Loading Data Lake parquet into SQL staging (`stg_flights`, `stg_weather_*`, `stg_airports`, `stg_geography`)
is an ADF Copy activity, not a Function call — there is no `*/load` endpoint.

- Put the actual ETL logic in `etl/`, keep `function_app.py` thin.
- New Python package? Add it to `requirements.txt`.
- Each call must finish in under about 3.5 minutes (ADF Azure Function activity limit).
- Merge to `main` → deployed automatically by `deploy-functions.yml`.
