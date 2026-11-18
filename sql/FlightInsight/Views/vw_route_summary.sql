-- One row per route and month, shaped for the Cosmos route_summaries documents
-- (cosmos/schemas/route_summary.schema.json). Scalar fields are flat columns named after their
-- document path (totals_* -> totals.*, delay_*_min -> delay_causes_min.*); the two arrays
-- (by_airline, best_departure_hours) are JSON strings.
-- best_departure_hours: the 3 local departure hours with the best on-time rate (>= 3 completed flights).
CREATE VIEW dbo.vw_route_summary
AS
WITH totals AS (
    SELECT route_key, month_key, origin, dest, distance_mi,
           COUNT(*) AS flights,
           SUM(is_cancelled) AS cancelled,
           SUM(is_diverted) AS diverted,
           CAST(1.0 * SUM(is_on_time) / NULLIF(SUM(is_completed), 0) AS DECIMAL(5, 4))
               AS on_time_rate,
           CAST(AVG(CASE WHEN is_completed = 1 THEN 1.0 * arr_delay_min END) AS DECIMAL(7, 2))
               AS avg_arr_delay_min
    FROM dbo.vw_flights
    GROUP BY route_key, month_key, origin, dest, distance_mi
),
p90 AS (
    SELECT DISTINCT route_key, month_key,
           PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY arr_delay_min)
               OVER (PARTITION BY route_key, month_key) AS p90_arr_delay_min
    FROM dbo.vw_flights
    WHERE is_completed = 1
),
causes AS (
    SELECT f.route_key, f.date_key / 100 AS month_key,
           SUM(CASE WHEN c.cause_code = 'carrier' THEN c.delay_minutes ELSE 0 END) AS carrier_min,
           SUM(CASE WHEN c.cause_code = 'weather' THEN c.delay_minutes ELSE 0 END) AS weather_min,
           SUM(CASE WHEN c.cause_code = 'nas' THEN c.delay_minutes ELSE 0 END) AS nas_min,
           SUM(CASE WHEN c.cause_code = 'security' THEN c.delay_minutes ELSE 0 END) AS security_min,
           SUM(CASE WHEN c.cause_code = 'late_aircraft' THEN c.delay_minutes ELSE 0 END)
               AS late_aircraft_min,
           SUM(c.delay_minutes) AS total_min
    FROM dbo.fact_flight_delay_causes AS c
    JOIN dbo.fact_flights AS f ON f.flight_id = c.flight_id
    GROUP BY f.route_key, f.date_key / 100
),
hours AS (
    SELECT route_key, month_key, dep_local_hour,
           SUM(is_completed) AS completed,
           1.0 * SUM(is_on_time) / NULLIF(SUM(is_completed), 0) AS on_time_rate
    FROM dbo.vw_flights
    GROUP BY route_key, month_key, dep_local_hour
)
SELECT t.origin + '-' + t.dest + '-' + CAST(t.month_key AS CHAR(6)) AS id,
       t.route_key,
       t.origin,
       t.dest,
       t.month_key,
       t.distance_mi,
       t.flights AS totals_flights,
       t.cancelled AS totals_cancelled,
       t.diverted AS totals_diverted,
       t.on_time_rate AS totals_on_time_rate,
       t.avg_arr_delay_min AS totals_avg_arr_delay_min,
       CAST(p.p90_arr_delay_min AS DECIMAL(7, 2)) AS totals_p90_arr_delay_min,
       CAST(1.0 * c.weather_min / NULLIF(c.total_min, 0) AS DECIMAL(5, 4))
           AS totals_weather_delay_share,
       ISNULL(c.carrier_min, 0) AS delay_carrier_min,
       ISNULL(c.weather_min, 0) AS delay_weather_min,
       ISNULL(c.nas_min, 0) AS delay_nas_min,
       ISNULL(c.security_min, 0) AS delay_security_min,
       ISNULL(c.late_aircraft_min, 0) AS delay_late_aircraft_min,
       (
           SELECT al.carrier_code, m.flights, m.cancelled, m.diverted, m.on_time_rate,
                  m.avg_arr_delay_min, m.p90_arr_delay_min, m.weather_delay_share
           FROM dbo.agg_route_monthly AS m
           JOIN dbo.dim_airlines AS al ON al.airline_key = m.airline_key
           WHERE m.route_key = t.route_key AND m.month_key = t.month_key
           FOR JSON PATH, INCLUDE_NULL_VALUES
       ) AS by_airline_json,
       (
           SELECT '[' + STRING_AGG(CAST(b.dep_local_hour AS VARCHAR(2)), ',')
                            WITHIN GROUP (ORDER BY b.dep_local_hour) + ']'
           FROM (
               SELECT TOP (3) hr.dep_local_hour
               FROM hours AS hr
               WHERE hr.route_key = t.route_key AND hr.month_key = t.month_key
                 AND hr.completed >= 3
               ORDER BY hr.on_time_rate DESC, hr.completed DESC
           ) AS b
       ) AS best_departure_hours_json
FROM totals AS t
LEFT JOIN p90 AS p ON p.route_key = t.route_key AND p.month_key = t.month_key
LEFT JOIN causes AS c ON c.route_key = t.route_key AND c.month_key = t.month_key;
