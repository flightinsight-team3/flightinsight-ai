-- Upserts dim_airports from the latest stg_airports snapshot. Run after usp_load_dim_geography.
-- Airports are never deleted: fact rows from older months may still reference them.
CREATE PROCEDURE dbo.usp_load_dim_airports
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @snapshot_key INT = (SELECT MAX(snapshot_key) FROM dbo.stg_airports);

    MERGE dbo.dim_airports AS t
    USING (
        SELECT a.iata_code, a.icao_code, a.airport_name, a.city, g.geo_key,
               a.latitude, a.longitude, a.timezone, a.hub_type, a.is_top30
        FROM dbo.stg_airports AS a
        LEFT JOIN dbo.dim_geography AS g ON g.state_code = a.state_code
        WHERE a.snapshot_key = @snapshot_key
    ) AS s
    ON t.iata_code = s.iata_code
    WHEN MATCHED THEN UPDATE SET
        icao_code    = s.icao_code,
        airport_name = s.airport_name,
        city         = s.city,
        geo_key      = s.geo_key,
        latitude     = s.latitude,
        longitude    = s.longitude,
        timezone     = s.timezone,
        hub_type     = s.hub_type,
        is_top30     = s.is_top30
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (iata_code, icao_code, airport_name, city, geo_key,
                latitude, longitude, timezone, hub_type, is_top30)
        VALUES (s.iata_code, s.icao_code, s.airport_name, s.city, s.geo_key,
                s.latitude, s.longitude, s.timezone, s.hub_type, s.is_top30);
END;
