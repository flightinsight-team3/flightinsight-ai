-- Grain: weather station x UTC hour (one observation kept per hour; rule documented in the ETL).
CREATE TABLE dbo.fact_weather_hourly (
    station_key      INT           NOT NULL,
    obs_hour_utc     DATETIME2(0)  NOT NULL,
    local_date_key   INT           NOT NULL,
    temperature_f    DECIMAL(5, 1) NULL,
    precipitation_in DECIMAL(5, 2) NULL,
    is_trace_precip  BIT           NOT NULL CONSTRAINT df_fwh_trace DEFAULT (0),
    wind_speed_mph   INT           NULL,
    wind_gust_mph    INT           NULL,
    visibility_mi    DECIMAL(5, 2) NULL,
    present_weather  VARCHAR(100)  NULL,
    is_adverse       BIT           NOT NULL CONSTRAINT df_fwh_adverse DEFAULT (0),
    CONSTRAINT pk_fact_weather_hourly PRIMARY KEY (station_key, obs_hour_utc),
    CONSTRAINT fk_fwh_station FOREIGN KEY (station_key) REFERENCES dbo.dim_weather_stations (station_key),
    CONSTRAINT fk_fwh_local_date FOREIGN KEY (local_date_key) REFERENCES dbo.dim_date (date_key)
);
