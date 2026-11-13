# sql/

`FlightInsight/` is a SQL Database Project: each table, view and procedure is one `.sql` file
describing its **final** shape (write `CREATE TABLE`, never `ALTER TABLE`). On deployment the tool
compares the project with the database and generates the needed changes itself.

| Folder | Contents |
|---|---|
| `Tables/Dimensions`, `Facts`, `Aggregates`, `Bridge` | The 16-table star schema |
| `Tables/Etl` | `etl_load_log`, `stg_rejected` (plus `stg_*` staging tables as the ETL needs them) |
| `Views/` | `vw_*` read-only views |
| `StoredProcedures/` | `usp_*` staging → star transforms |
| `Scripts/PostDeployment.sql` | Idempotent seed data for small reference tables |

- **Check locally (optional):** `dotnet build sql/FlightInsight/FlightInsight.sqlproj`
- **Try on dev:** Actions → Deploy SQL schema → Run workflow → your branch → `dev`
- **Prod:** merge to `main`; it deploys automatically.

Changes that would drop data (dropping a column, shrinking a type) are blocked. If you really need one,
discuss it with the team first.
