# functions/

Python Azure Functions app (Flex Consumption). ADF calls these HTTP endpoints in order.

| Endpoint | Module | Step |
|---|---|---|
| `POST /api/bts/ingest` | `etl/bts.py` | Download, clean, UTC, validate → Data Lake |
| `POST /api/bts/load` | `etl/bts.py` | Data Lake → SQL staging |
| `POST /api/noaa/ingest` | `etl/noaa.py` | Same for weather |
| `POST /api/noaa/load` | `etl/noaa.py` | |
| `POST /api/graph/load` | `etl/graph.py` | `agg_route_monthly` → Gremlin graph |

- Put the actual ETL logic in `etl/`, keep `function_app.py` thin.
- New Python package? Add it to `requirements.txt`.
- Each call must finish in under about 3.5 minutes (ADF Azure Function activity limit).
- Merge to `main` → deployed automatically by `deploy-functions.yml`.
