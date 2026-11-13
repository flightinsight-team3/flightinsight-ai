# Architecture

## Data flow

```mermaid
flowchart TB
  subgraph Sources
    BTS[BTS On-Time CSV]
    NOAA[NOAA LCD hourly + daily]
    REF[OurAirports + Census]
    ASRS[NASA ASRS export]
  end

  subgraph rg["rg-flightinsight-core (one subscription)"]
    ADF[Data Factory<br/>orchestration]
    FN[Azure Functions<br/>Python ETL]
    LAKE[(Data Lake<br/>raw / clean)]
    SQL[(Azure SQL · Canada Central<br/>staging → star schema → views)]
    KV[Key Vault]
    DOCS[(Cosmos NoSQL · free tier<br/>route_summaries · asrs_reports + vectors)]
    G[(Cosmos Gremlin · serverless<br/>route_network)]
  end

  LAPTOP[Laptop: Ollama embeddings<br/>scripts/embed_asrs.py]
  BI[Power BI]
  BOT[LangChain + Streamlit<br/>later]

  BTS & NOAA & REF --> FN
  ADF -- calls --> FN
  FN --> LAKE --> FN --> SQL
  ADF -- stored procedures --> SQL
  ADF -- copy vw_route_summary --> DOCS
  FN -- graph/load --> G
  ASRS --> LAPTOP --> DOCS
  SQL --> BI
  DOCS & G --> BOT
  KV -. secrets .- FN & ADF
```

## Monthly pipeline (one ADF run per month_key)

1. `bts/ingest`, `noaa/ingest` (Functions) — download to `raw/`, clean + UTC + validate to `clean/`
2. `bts/load`, `noaa/load` (Functions) — delete-and-reload the month in SQL staging
3. Stored Procedure activities — staging → dimensions → facts → `agg_route_monthly`
4. Copy activity — `vw_route_summary` → Cosmos `route_summaries`
5. `graph/load` (Function) — yearly route edges → Gremlin
6. Every step writes to `etl_load_log`; bad rows go to `stg_rejected`

ASRS embeddings are a one-off batch run from a laptop, not part of the monthly pipeline.

## Decisions (changes from the P2 design)

| Decision | Why |
|---|---|
| ADF + Azure Functions instead of local Airflow | Fully cloud-hosted and deployable by CI/CD; no always-on Airflow server to pay for; the data is a 2024 backfill so orchestration needs are light |
| Data Lake landing zone (`raw` / `clean`) | Re-runs don't re-download; raw files are kept for audit |
| Each `ingest` / `load` is a separate Function call | The ADF Azure Function activity times out at about 230 s |
| All resources in one subscription and resource group | One GitHub environment and one OIDC identity; services authorize each other with managed identities, no cross-subscription keys |
| Cosmos NoSQL on the free tier, Gremlin serverless | Only one free-tier Cosmos account is allowed per subscription; NoSQL is used most, the graph is loaded once a year and queried lightly |
| Azure SQL in Canada Central, everything else in West US 2 | The subscription may only use five regions, and SQL provisioning is restricted in West US 2; cross-region latency is irrelevant for batch ETL |
| Two SQL databases: `flightinsight` (prod) and `flightinsight-dev` | Free; experiments in dev can't break the pipeline; prod changes only via `main` |
| No local databases or Docker | Everyone works against the same cloud state; the SQL project is validated in CI without a database |
| SQL Database Project (declarative) instead of migration scripts | The repo always shows each table's current shape; CI catches broken references; data-loss changes are blocked |
| Cosmos NoSQL throughput hard-capped at 1000 RU/s | Stays inside the free tier |
