# Gremlin graph model (`route_network`)

Cosmos DB does not enforce this model; `functions/etl/graph.py` must follow it.
Every vertex needs a `pk` property (the graph's partition key).

| Element | Label | id | pk | Properties |
|---|---|---|---|---|
| Vertex | `airport` | IATA code, e.g. `SEA` | state code, e.g. `WA` | airport_name, city, state_code, hub_type, is_top30 |
| Vertex | `airline` | carrier code, e.g. `AS` | `airline` | airline_name |
| Edge | `route` (airport → airport) | `route-<route_key>-<year>` | — | route_key, flights, on_time_rate, avg_arr_delay_min, cancel_rate, distance_mi, year |
| Edge | `operates_at` (airline → airport) | `<carrier>-<iata>-<year>` | — | flights, share_of_airport, year |

Edges are stored in the partition of their out-vertex. Property names match Azure SQL column names.
Loads must be upserts (re-running a year must not duplicate vertices or edges).
