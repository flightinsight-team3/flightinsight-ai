# FlightInsight AI

Analyzing U.S. flight delays, weather impact, and route network reliability on Microsoft Azure.
Team 3 — Jing Chen, Jing Yang Wang, Jinkun Zhao, Chi Zhang.

Architecture: Azure Data Factory orchestrates Python ETL running in Azure Functions. Raw files land in a
Data Lake, structured data goes into an Azure SQL star schema, and aggregates flow on to Cosmos DB
(NoSQL documents + vectors, and a Gremlin graph). See [docs/architecture.md](docs/architecture.md).

## Where does my code go?

| I'm working on… | Put it in | How it reaches Azure |
|---|---|---|
| Azure resources (storage, SQL server, Cosmos accounts, ADF, Key Vault, Function App) | `infra/` (Bicep; `core.bicep` is the entry point) | **Deploy infrastructure** workflow (manual) |
| Tables, views, stored procedures | `sql/FlightInsight/` | **Deploy SQL schema** workflow (automatic on merge) |
| Python ETL logic (download, clean, UTC, validate, load) | `functions/etl/` | **Deploy Functions** workflow (automatic on merge) |
| HTTP endpoints that ADF calls | `functions/function_app.py` | **Deploy Functions** workflow |
| ADF pipelines, datasets, linked services, triggers | `adf/` (written by ADF Studio, don't edit by hand) | Publish from ADF Studio |
| Cosmos document shapes and graph model | `cosmos/` | Checked by CI |
| One-off scripts (e.g. ASRS embeddings with Ollama) | `scripts/` | Run manually |
| Power BI reports | `powerbi/` (`.pbip` format) | Published from Power BI Desktop |
| Chatbot (LangChain + Streamlit), later | `app/` | Later |
| Tests | `tests/` | Run by CI on every PR |
| Design notes and decisions | `docs/` | — |

Every folder has a short README explaining what belongs there.

## How we work

1. Create a branch for each piece of work (any name, e.g. `jchen-dim-tables`).
2. Open a pull request into `main`. CI must pass, then merge. Write `Closes #<issue>` if there is an issue.

Merging into `main` deploys automatically, so `main` always matches what is running in Azure.

## CI/CD workflows

| Workflow | Runs when | What it does |
|---|---|---|
| `ci.yml` | Every PR and every push to `main` | Lints and tests Python, builds the SQL project (catches broken tables/views without a database), compiles Bicep |
| `deploy-sql.yml` | Merge to `main` touching `sql/` → **prod** database. Manual run → choose **dev** or **prod** | Publishes the schema with data-loss protection on |
| `deploy-functions.yml` | Merge to `main` touching `functions/` | Deploys the Function App |
| `deploy-infra.yml` | Manual only | Previews (what-if) and, with *apply* checked, deploys `infra/core.bicep` |

**Try your branch on the dev database:** Actions → Deploy SQL schema → Run workflow → pick your branch → target `dev`.

## Azure layout

Everything lives in one subscription and one resource group, deployed by the `core` GitHub environment.

| Resource group | Region | Contains |
|---|---|---|
| `rg-flightinsight-core` | West US 2 | Data Lake, Key Vault, Data Factory, Function App, Cosmos DB for NoSQL (`route_summaries`, `asrs_reports` with vector search, free tier), Cosmos DB for Gremlin (`route_network`, serverless) |
| | Canada Central | Azure SQL (`flightinsight` + `flightinsight-dev`, free offer) — SQL is not available in West US 2 for this subscription |

One-time setup for connecting GitHub to Azure: [docs/azure-cicd-setup.md](docs/azure-cicd-setup.md).

## Secrets

Never commit passwords, keys or connection strings. They live in Azure Key Vault and in GitHub environment
secrets. Copy `.env.example` to `.env` for anything you run on your laptop; `.env` is git-ignored.
