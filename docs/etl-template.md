# ETL template: how to add a data source

`functions/etl/bts.py` (DS01) is the reference implementation. Copy its structure for NOAA (DS02),
airports (DS03) and any other source.

## The flow

```
source ──download()──► raw/<source>/<yyyymm>/…          exactly as published, never modified
                 │
           read_raw() → validate() → transform()        pure pandas, unit-tested, no Azure
                 │
                 ├────► clean/<source>/<yyyymm>/<table>.parquet    columns = dbo.stg_<table>
                 └────► clean/<source>/<yyyymm>/rejected.parquet   columns = dbo.stg_rejected
                                    │
                      ADF Copy activity → dbo.stg_* → stored procedures → star schema
```

Python stops at parquet in the Data Lake. Loading into SQL is an ADF Copy activity, and
staging → dimensions/facts is T-SQL stored procedures.

## Rules every source follows

| Rule | Why |
|---|---|
| One module per source: `functions/etl/<source>.py` with `SOURCE = "<source>"` | Predictable layout |
| Functions `download`, `read_raw`, `validate`, `transform`, `ingest_month` | Same shape everywhere; ADF and the CLI call `ingest_month` |
| `read_raw` reads everything as strings (`dtype=str, keep_default_na=False`) | No silent type guessing; leading zeros and empty values survive |
| `validate` returns one reason per row, `""` = valid | Bad rows are kept with a reason in `stg_rejected`, never silently dropped |
| Out-of-scope rows (e.g. not Top 30) are counted, not rejected | Rejected means "broken data", not "not needed" |
| `transform` takes lookups as parameters (e.g. `airport_tz`) | Tests pass small dicts; no network or database in tests |
| Clean columns are a constant (`STG_COLUMNS`) equal to the staging table | A test checks it; the ADF copy maps by name |
| Times are stored in UTC (`*_utc`); local values only where analysis needs them | Flights and weather join by UTC hour |
| `ingest_month` overwrites its month's files | Re-running never creates duplicates |
| Writes go through a `Sink` (`LakeSink` or `LocalSink`) | Same code on a laptop and in Azure |
| Scope settings live in `etl/config.py` (e.g. `TOP30_AIRPORTS`) | One place to change, shared by all sources |

## Adding a source, step by step

1. Download one month by hand into `data/<source>/` (git-ignored) and look at it: columns, formats, empty values.
2. Create `functions/etl/<source>.py` from `bts.py`: `RAW_COLUMNS`, `REQUIRED_COLUMNS`, `STG_COLUMNS`, the five functions.
3. Add `sql/FlightInsight/Tables/Etl/stg_<table>.sql` with exactly `STG_COLUMNS`.
4. Write `tests/test_<source>.py` with a `row(**overrides)` helper in the real file's string format.
   Cover: a normal row, each rejection reason, out-of-scope rows, duplicates, edge cases of the source.
5. Register the source in `functions/etl/run.py` (`SOURCES`) and add an endpoint in `functions/function_app.py`.
6. Run locally: `cd functions && python -m etl.run <source> 202401 --local`, check `data/lake/`.
7. PR → CI runs the tests and builds the SQL project.

## Running BTS locally

```bash
pip install -r functions/requirements.txt
cd functions
python -m etl.run bts 202401 --local --raw-file ../data/bts/bts_2024_01.zip   # no download
python -m etl.run bts 202401 --local                                          # downloads from BTS
python -m etl.run bts 202401                                                  # writes to the Data Lake
```

The last command needs `az login` and **Storage Blob Data Contributor** on the Data Lake.
If BTS's certificate fails on your network, set `BTS_VERIFY_SSL=false`.
