# cosmos/

Cosmos DB has no fixed schema, so the shape of every document is defined here and checked by CI.
Accounts, containers, partition keys and the vector policy are in `infra/nosql.bicep` and `infra/graph.bicep`.

| File | Describes |
|---|---|
| `schemas/route_summary.schema.json` | `route_summaries` documents (written by the ADF copy from `vw_route_summary`) |
| `schemas/asrs_report.schema.json` | `asrs_reports` documents with `narrative_vector` |
| `samples/*.sample.json` | One valid example per schema; CI validates them |
| `graph-model.md` | Gremlin vertices and edges |

Change a document shape → update the schema and the sample in the same PR.
