-- Grain: one row per flight with its matched origin/destination observation (keys only, no values).
CREATE TABLE dbo.fact_flight_weather (
    flight_id            BIGINT       NOT NULL,
    origin_station_key   INT          NULL,
    origin_obs_hour_utc  DATETIME2(0) NULL,
    dest_station_key     INT          NULL,
    dest_obs_hour_utc    DATETIME2(0) NULL,
    origin_time_gap_min  INT          NULL,
    dest_time_gap_min    INT          NULL,
    CONSTRAINT pk_fact_flight_weather PRIMARY KEY (flight_id),
    CONSTRAINT fk_ffw_flight FOREIGN KEY (flight_id) REFERENCES dbo.fact_flights (flight_id),
    CONSTRAINT fk_ffw_origin_obs FOREIGN KEY (origin_station_key, origin_obs_hour_utc)
        REFERENCES dbo.fact_weather_hourly (station_key, obs_hour_utc),
    CONSTRAINT fk_ffw_dest_obs FOREIGN KEY (dest_station_key, dest_obs_hour_utc)
        REFERENCES dbo.fact_weather_hourly (station_key, obs_hour_utc)
);
