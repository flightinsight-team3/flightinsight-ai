-- Links each airport to the weather station at the same ICAO code (one primary station per airport).
CREATE PROCEDURE dbo.usp_load_bridge_airport_station
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    MERGE dbo.bridge_airport_station AS t
    USING (
        SELECT a.airport_key,
               w.station_key,
               CASE
                   WHEN a.latitude IS NOT NULL AND a.longitude IS NOT NULL
                    AND w.latitude IS NOT NULL AND w.longitude IS NOT NULL
                   THEN CAST(
                       geography::Point(a.latitude, a.longitude, 4326).STDistance(
                           geography::Point(w.latitude, w.longitude, 4326)) / 1000.0
                       AS DECIMAL(7, 2))
               END AS distance_km
        FROM dbo.dim_airports AS a
        JOIN dbo.dim_weather_stations AS w ON w.icao_code = a.icao_code
    ) AS s
    ON t.airport_key = s.airport_key AND t.station_key = s.station_key
    WHEN MATCHED THEN UPDATE SET
        distance_km    = s.distance_km,
        mapping_method = 'icao_match',
        is_primary     = 1
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (airport_key, station_key, distance_km, mapping_method, is_primary)
        VALUES (s.airport_key, s.station_key, s.distance_km, 'icao_match', 1);
END;
