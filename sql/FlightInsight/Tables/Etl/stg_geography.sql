-- Staging for DS03 US geography: one row per US state / DC, exactly the columns of
-- clean/airports/<snapshot_key>/geography.parquet
-- (see functions/etl/airports.py STG_GEOGRAPHY_COLUMNS).
-- Built from a static table embedded in the ETL module, not downloaded from Census.
CREATE TABLE dbo.stg_geography (
    snapshot_key  INT         NOT NULL,
    state_code    CHAR(2)     NOT NULL,
    state_name    VARCHAR(50) NOT NULL,
    state_fips    CHAR(2)     NOT NULL,
    census_region VARCHAR(20) NOT NULL
);
GO

CREATE INDEX ix_stg_geography_snapshot ON dbo.stg_geography (snapshot_key);
