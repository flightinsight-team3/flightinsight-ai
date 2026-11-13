# infra/

Bicep templates for every Azure resource. Change resources here, not by clicking in the portal,
so the environment can always be rebuilt from git.

| File | Role | Resources |
|---|---|---|
| `core.bicep` | **Entry point**, deployed into `rg-flightinsight-core` | Data Lake, Azure SQL (2 free DBs), Key Vault, Data Factory, Function App, service permissions; calls the two modules below |
| `nosql.bicep` | Module | Cosmos DB for NoSQL (free tier) with `route_summaries` and `asrs_reports` (vector policy), data access for ADF and Functions |
| `graph.bicep` | Module | Cosmos DB for Gremlin (serverless) with the `route_network` graph |
| `params/core.bicepparam` | Parameters | Regions (`location`, `sqlLocation`, `cosmosLocation`) and the SQL password from the environment |

Deploy: Actions → **Deploy infrastructure** → `core` → run once with *apply* unchecked to preview,
then again with *apply* checked.

Cosmos partition keys cannot be changed after a container is created. Changing them here requires
deleting and recreating the container. Key Vault has soft delete: don't delete it, or its name is
blocked for 7 days.
