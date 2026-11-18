-- Staging for DS02 NOAA station metadata: one row per station for the current snapshot,
-- exactly the columns of clean/noaa/<yyyymm>/stations.parquet
-- (see functions/etl/noaa.py STG_STATION_COLUMNS).
CREATE TABLE dbo.stg_weather_stations (
    snapshot_key INT           NOT NULL,
    station_id   VARCHAR(20)   NOT NULL,
    icao_code    CHAR(4)       NULL,
    station_name VARCHAR(200)  NOT NULL,
    latitude     DECIMAL(9, 6) NULL,
    longitude    DECIMAL(9, 6) NULL
);
GO

CREATE INDEX ix_stg_weather_stations_snapshot ON dbo.stg_weather_stations (snapshot_key);
