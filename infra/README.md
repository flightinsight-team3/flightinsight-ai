# infra/

Bicep templates for every Azure resource. Change resources here, not by clicking in the portal,
so the environment can always be rebuilt from git.

| File | Deploys into | Resources |
|---|---|---|
| `core.bicep` | `rg-flightinsight-core` | Data Lake, Azure SQL (2 free DBs), Key Vault, Data Factory, Function App, service permissions |
| `nosql.bicep` | `rg-flightinsight-nosql` | Cosmos DB for NoSQL with `route_summaries` and `asrs_reports` (vector policy) |
| `graph.bicep` | `rg-flightinsight-graph` | Cosmos DB for Gremlin with the `route_network` graph |
| `params/*.bicepparam` | — | Parameter values per component (no secrets) |

Deploy: Actions → **Deploy infrastructure** → choose component → run once with *apply* unchecked to
preview, then again with *apply* checked.

Cosmos partition keys cannot be changed after a container is created. Changing them here requires
deleting and recreating the container.
