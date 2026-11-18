-- Staging for DS02 NOAA hourly observations: one row per station-hour, exactly the columns of
-- clean/noaa/<yyyymm>/hourly.parquet (see functions/etl/noaa.py STG_HOURLY_COLUMNS).
-- Loaded by an ADF Copy activity; each month is deleted and reloaded as a unit.
CREATE TABLE dbo.stg_weather_hourly (
    month_key        INT           NOT NULL,
    station_id       VARCHAR(20)   NOT NULL,
    obs_hour_utc     DATETIME2(0)  NOT NULL,
    local_date_key   INT           NOT NULL,
    temperature_f    DECIMAL(5, 1) NULL,
    precipitation_in DECIMAL(5, 2) NULL,
    is_trace_precip  BIT           NOT NULL,
    wind_speed_mph   INT           NULL,
    wind_gust_mph    INT           NULL,
    visibility_mi    DECIMAL(5, 2) NULL,
    present_weather  VARCHAR(100)  NULL,
    is_adverse       BIT           NOT NULL
);
GO

CREATE INDEX ix_stg_weather_hourly_month ON dbo.stg_weather_hourly (month_key);
