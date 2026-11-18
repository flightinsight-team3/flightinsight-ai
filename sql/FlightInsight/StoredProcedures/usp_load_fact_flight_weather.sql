-- Rebuilds fact_flight_weather for the flights of @month_key: each flight gets the primary station
-- of its origin/destination and the observation of the UTC hour of scheduled departure/arrival.
-- Stations or hours with no observation stay NULL. Run after usp_load_fact_weather and usp_load_fact_flights.
CREATE PROCEDURE dbo.usp_load_fact_flight_weather
    @month_key INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @first_date_key INT = @month_key * 100 + 1;
    DECLARE @last_date_key INT = @month_key * 100 + 31;

    DELETE w
    FROM dbo.fact_flight_weather AS w
    JOIN dbo.fact_flights AS f ON f.flight_id = w.flight_id
    WHERE f.date_key BETWEEN @first_date_key AND @last_date_key;

    INSERT INTO dbo.fact_flight_weather (
        flight_id, origin_station_key, origin_obs_hour_utc, dest_station_key, dest_obs_hour_utc,
        origin_time_gap_min, dest_time_gap_min)
    SELECT f.flight_id,
           bo.station_key, ho.obs_hour_utc,
           bd.station_key, hd.obs_hour_utc,
           DATEDIFF(MINUTE, ho.obs_hour_utc, f.sched_dep_utc),
           DATEDIFF(MINUTE, hd.obs_hour_utc, f.sched_arr_utc)
    FROM dbo.fact_flights AS f
    JOIN dbo.dim_routes AS r ON r.route_key = f.route_key
    CROSS APPLY (
        SELECT CAST(DATEADD(HOUR, DATEDIFF(HOUR, 0, f.sched_dep_utc), 0) AS DATETIME2(0)) AS dep_hour,
               CAST(DATEADD(HOUR, DATEDIFF(HOUR, 0, f.sched_arr_utc), 0) AS DATETIME2(0)) AS arr_hour
    ) AS t
    OUTER APPLY (
        SELECT TOP (1) b.station_key
        FROM dbo.bridge_airport_station AS b
        WHERE b.airport_key = r.origin_airport_key AND b.is_primary = 1
        ORDER BY b.distance_km
    ) AS bo
    OUTER APPLY (
        SELECT TOP (1) b.station_key
        FROM dbo.bridge_airport_station AS b
        WHERE b.airport_key = r.dest_airport_key AND b.is_primary = 1
        ORDER BY b.distance_km
    ) AS bd
    LEFT JOIN dbo.fact_weather_hourly AS ho
      ON ho.station_key = bo.station_key AND ho.obs_hour_utc = t.dep_hour
    LEFT JOIN dbo.fact_weather_hourly AS hd
      ON hd.station_key = bd.station_key AND hd.obs_hour_utc = t.arr_hour
    WHERE f.date_key BETWEEN @first_date_key AND @last_date_key;
END;
