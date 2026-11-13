CREATE TABLE dbo.dim_weather_stations (
    station_key  INT IDENTITY(1, 1) NOT NULL,
    station_id   VARCHAR(20)        NOT NULL,  -- NOAA LCD station id
    icao_code    CHAR(4)            NULL,
    station_name VARCHAR(200)       NOT NULL,
    latitude     DECIMAL(9, 6)      NULL,
    longitude    DECIMAL(9, 6)      NULL,
    CONSTRAINT pk_dim_weather_stations PRIMARY KEY (station_key),
    CONSTRAINT uq_dim_weather_stations_station_id UNIQUE (station_id)
);
