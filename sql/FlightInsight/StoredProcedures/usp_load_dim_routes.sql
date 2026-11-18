-- Adds the directed airport pairs flown in stg_flights for @month_key. Run after usp_load_dim_airports.
-- Flights whose airports are not in dim_airports get no route and are skipped by usp_load_fact_flights.
CREATE PROCEDURE dbo.usp_load_dim_routes
    @month_key INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    MERGE dbo.dim_routes AS t
    USING (
        SELECT o.airport_key AS origin_airport_key,
               d.airport_key AS dest_airport_key,
               MAX(f.distance_mi) AS distance_mi
        FROM dbo.stg_flights AS f
        JOIN dbo.dim_airports AS o ON o.iata_code = f.origin
        JOIN dbo.dim_airports AS d ON d.iata_code = f.dest
        WHERE f.month_key = @month_key
          AND o.airport_key <> d.airport_key
        GROUP BY o.airport_key, d.airport_key
    ) AS s
    ON t.origin_airport_key = s.origin_airport_key AND t.dest_airport_key = s.dest_airport_key
    WHEN MATCHED AND t.distance_mi IS NULL AND s.distance_mi IS NOT NULL THEN UPDATE SET
        distance_mi = s.distance_mi
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (origin_airport_key, dest_airport_key, distance_mi)
        VALUES (s.origin_airport_key, s.dest_airport_key, s.distance_mi);
END;
