-- Grain: weather station x day. LCD has no hourly snowfall, so snow lives here. Missing = NULL, not 0.
CREATE TABLE dbo.fact_weather_daily (
    station_key      INT           NOT NULL,
    date_key         INT           NOT NULL,
    snowfall_in      DECIMAL(5, 1) NULL,
    snow_depth_in    DECIMAL(5, 1) NULL,
    precipitation_in DECIMAL(5, 2) NULL,
    CONSTRAINT pk_fact_weather_daily PRIMARY KEY (station_key, date_key),
    CONSTRAINT fk_fwd_station FOREIGN KEY (station_key) REFERENCES dbo.dim_weather_stations (station_key),
    CONSTRAINT fk_fwd_date FOREIGN KEY (date_key) REFERENCES dbo.dim_date (date_key)
);
