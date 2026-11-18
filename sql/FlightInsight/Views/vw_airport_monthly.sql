-- Origin airport x month: departures and how punctual they were.
-- dep_on_time_rate uses departure delay (< 15 min) among flights that departed.
CREATE VIEW dbo.vw_airport_monthly
AS
SELECT f.month_key,
       f.origin AS iata_code,
       f.origin_airport_name AS airport_name,
       f.origin_city AS city,
       f.origin_state AS state_code,
       a.is_top30,
       COUNT(*) AS departures,
       SUM(f.is_cancelled) AS cancelled,
       CAST(1.0 * SUM(f.is_cancelled) / COUNT(*) AS DECIMAL(5, 4)) AS cancel_rate,
       CAST(1.0 * SUM(CASE WHEN f.dep_delay_min < 15 THEN 1 ELSE 0 END)
            / NULLIF(SUM(CASE WHEN f.dep_delay_min IS NOT NULL THEN 1 ELSE 0 END), 0)
            AS DECIMAL(5, 4)) AS dep_on_time_rate,
       CAST(1.0 * SUM(f.is_on_time) / NULLIF(SUM(f.is_completed), 0) AS DECIMAL(5, 4))
           AS arr_on_time_rate,
       CAST(AVG(1.0 * f.dep_delay_min) AS DECIMAL(7, 2)) AS avg_dep_delay_min,
       CAST(AVG(1.0 * f.taxi_out_min) AS DECIMAL(7, 2)) AS avg_taxi_out_min,
       COUNT(DISTINCT f.dest) AS destinations
FROM dbo.vw_flights AS f
JOIN dbo.dim_airports AS a ON a.iata_code = f.origin
GROUP BY f.month_key, f.origin, f.origin_airport_name, f.origin_city, f.origin_state, a.is_top30;
