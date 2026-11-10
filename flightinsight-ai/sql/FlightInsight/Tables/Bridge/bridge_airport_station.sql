CREATE TABLE dbo.bridge_airport_station (
    airport_key    INT           NOT NULL,
    station_key    INT           NOT NULL,
    distance_km    DECIMAL(7, 2) NULL,
    mapping_method VARCHAR(30)   NOT NULL,  -- e.g. icao_match, nearest
    is_primary     BIT           NOT NULL,
    CONSTRAINT pk_bridge_airport_station PRIMARY KEY (airport_key, station_key),
    CONSTRAINT fk_bridge_airport FOREIGN KEY (airport_key) REFERENCES dbo.dim_airports (airport_key),
    CONSTRAINT fk_bridge_station FOREIGN KEY (station_key) REFERENCES dbo.dim_weather_stations (station_key)
);
