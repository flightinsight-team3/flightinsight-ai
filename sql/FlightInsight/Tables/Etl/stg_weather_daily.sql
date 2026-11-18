-- Staging for DS02 NOAA daily summaries: one row per station-day, exactly the columns of
-- clean/noaa/<yyyymm>/daily.parquet (see functions/etl/noaa.py STG_DAILY_COLUMNS).
CREATE TABLE dbo.stg_weather_daily (
    month_key        INT           NOT NULL,
    station_id       VARCHAR(20)   NOT NULL,
    date_key         INT           NOT NULL,
    snowfall_in      DECIMAL(5, 1) NULL,
    snow_depth_in    DECIMAL(5, 1) NULL,
    precipitation_in DECIMAL(5, 2) NULL
);
GO

CREATE INDEX ix_stg_weather_daily_month ON dbo.stg_weather_daily (month_key);
