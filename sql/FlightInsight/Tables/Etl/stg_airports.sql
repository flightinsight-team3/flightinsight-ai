-- Staging for DS03 OurAirports: one row per US airport with an IATA code, exactly
-- the columns of clean/airports/<snapshot_key>/airports.parquet
-- (see functions/etl/airports.py STG_AIRPORT_COLUMNS).
-- Loaded by an ADF Copy activity; the whole table is reloaded per snapshot.
-- No foreign keys here: staging holds codes; stored procedures resolve them to keys.
CREATE TABLE dbo.stg_airports (
    snapshot_key INT           NOT NULL,
    iata_code    CHAR(3)       NOT NULL,
    icao_code    CHAR(4)       NULL,
    airport_name VARCHAR(200)  NOT NULL,
    city         VARCHAR(100)  NULL,
    state_code   CHAR(2)       NOT NULL,
    latitude     DECIMAL(9, 6) NOT NULL,
    longitude    DECIMAL(9, 6) NOT NULL,
    timezone     VARCHAR(50)   NOT NULL,
    hub_type     VARCHAR(20)   NOT NULL,
    is_top30     BIT           NOT NULL
);
GO

CREATE INDEX ix_stg_airports_snapshot ON dbo.stg_airports (snapshot_key);
