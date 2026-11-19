-- Month x scheduled local departure hour: how delays build up over the day.
CREATE VIEW dbo.vw_delay_by_hour
AS
SELECT month_key,
       dep_local_hour,
       time_band,
       COUNT(*) AS flights,
       CAST(1.0 * SUM(is_cancelled) / COUNT(*) AS DECIMAL(5, 4)) AS cancel_rate,
       CAST(1.0 * SUM(is_on_time) / NULLIF(SUM(is_completed), 0) AS DECIMAL(5, 4)) AS on_time_rate,
       CAST(AVG(CASE WHEN is_completed = 1 THEN 1.0 * arr_delay_min END) AS DECIMAL(7, 2))
           AS avg_arr_delay_min
FROM dbo.vw_flights
GROUP BY month_key, dep_local_hour, time_band;
