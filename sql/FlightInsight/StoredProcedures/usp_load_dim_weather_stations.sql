-- Upserts dim_weather_stations from the latest stg_weather_stations snapshot.
CREATE PROCEDURE dbo.usp_load_dim_weather_stations
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @snapshot_key INT = (SELECT MAX(snapshot_key) FROM dbo.stg_weather_stations);

    MERGE dbo.dim_weather_stations AS t
    USING (
        SELECT station_id, icao_code, station_name, latitude, longitude
        FROM dbo.stg_weather_stations
        WHERE snapshot_key = @snapshot_key
    ) AS s
    ON t.station_id = s.station_id
    WHEN MATCHED THEN UPDATE SET
        icao_code    = s.icao_code,
        station_name = s.station_name,
        latitude     = s.latitude,
        longitude    = s.longitude
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (station_id, icao_code, station_name, latitude, longitude)
        VALUES (s.station_id, s.icao_code, s.station_name, s.latitude, s.longitude);
END;
