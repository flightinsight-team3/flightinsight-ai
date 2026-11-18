-- Deletes and reloads agg_route_monthly for @month_key from fact_flights and fact_flight_delay_causes.
-- On-time = completed (not cancelled, not diverted) flight arriving less than 15 minutes late.
-- weather_delay_share = weather delay minutes / all cause minutes on the route-airline.
CREATE PROCEDURE dbo.usp_load_agg_route_monthly
    @month_key INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @first_date_key INT = @month_key * 100 + 1;
    DECLARE @last_date_key INT = @month_key * 100 + 31;

    DELETE FROM dbo.agg_route_monthly WHERE month_key = @month_key;

    WITH flights AS (
        SELECT flight_id, route_key, airline_key, arr_delay_min,
               CAST(is_cancelled AS INT) AS cancelled,
               CAST(is_diverted AS INT) AS diverted,
               CASE WHEN is_cancelled = 0 AND is_diverted = 0 AND arr_delay_min IS NOT NULL
                    THEN 1 ELSE 0 END AS completed
        FROM dbo.fact_flights
        WHERE date_key BETWEEN @first_date_key AND @last_date_key
    ),
    p90 AS (
        SELECT DISTINCT route_key, airline_key,
               PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY arr_delay_min)
                   OVER (PARTITION BY route_key, airline_key) AS p90_arr_delay_min
        FROM flights
        WHERE completed = 1
    ),
    causes AS (
        SELECT f.route_key, f.airline_key,
               SUM(c.delay_minutes) AS total_minutes,
               SUM(CASE WHEN c.cause_code = 'weather' THEN c.delay_minutes ELSE 0 END)
                   AS weather_minutes
        FROM flights AS f
        JOIN dbo.fact_flight_delay_causes AS c ON c.flight_id = f.flight_id
        GROUP BY f.route_key, f.airline_key
    ),
    totals AS (
        SELECT route_key, airline_key,
               COUNT(*) AS flights,
               SUM(cancelled) AS cancelled,
               SUM(diverted) AS diverted,
               AVG(CASE WHEN completed = 1
                        THEN CASE WHEN arr_delay_min < 15 THEN 1.0 ELSE 0.0 END END) AS on_time_rate,
               AVG(CASE WHEN completed = 1 THEN CAST(arr_delay_min AS DECIMAL(9, 2)) END)
                   AS avg_arr_delay_min
        FROM flights
        GROUP BY route_key, airline_key
    )
    INSERT INTO dbo.agg_route_monthly (
        route_key, airline_key, month_key, flights, cancelled, diverted,
        on_time_rate, avg_arr_delay_min, p90_arr_delay_min, weather_delay_share)
    SELECT t.route_key, t.airline_key, @month_key, t.flights, t.cancelled, t.diverted,
           CAST(t.on_time_rate AS DECIMAL(5, 4)),
           CAST(t.avg_arr_delay_min AS DECIMAL(7, 2)),
           CAST(p.p90_arr_delay_min AS DECIMAL(7, 2)),
           CAST(CASE WHEN c.total_minutes > 0
                     THEN 1.0 * c.weather_minutes / c.total_minutes END AS DECIMAL(5, 4))
    FROM totals AS t
    LEFT JOIN p90 AS p ON p.route_key = t.route_key AND p.airline_key = t.airline_key
    LEFT JOIN causes AS c ON c.route_key = t.route_key AND c.airline_key = t.airline_key;
END;
