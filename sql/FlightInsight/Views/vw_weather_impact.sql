-- Month x weather condition at the origin in the scheduled departure hour: does bad weather hurt punctuality?
-- Conditions come from the LCD present-weather codes (SN snow, TS thunderstorm, FG fog, RA/DZ rain),
-- checked in that order of severity. Flights from airports without a station fall in 'No observation'.
CREATE VIEW dbo.vw_weather_impact
AS
SELECT f.month_key,
       c.origin_condition,
       COUNT(*) AS flights,
       CAST(1.0 * SUM(f.is_cancelled) / COUNT(*) AS DECIMAL(5, 4)) AS cancel_rate,
       CAST(1.0 * SUM(f.is_on_time) / NULLIF(SUM(f.is_completed), 0) AS DECIMAL(5, 4)) AS on_time_rate,
       CAST(AVG(CASE WHEN f.is_cancelled = 0 THEN 1.0 * f.dep_delay_min END) AS DECIMAL(7, 2))
           AS avg_dep_delay_min,
       CAST(AVG(CASE WHEN f.is_completed = 1 THEN 1.0 * f.arr_delay_min END) AS DECIMAL(7, 2))
           AS avg_arr_delay_min
FROM dbo.vw_flights AS f
CROSS APPLY (
    SELECT CASE
               WHEN f.origin_is_adverse IS NULL THEN 'No observation'
               WHEN f.origin_present_weather LIKE '%SN%' THEN 'Snow'
               WHEN f.origin_present_weather LIKE '%TS%' THEN 'Thunderstorm'
               WHEN f.origin_present_weather LIKE '%FG%' OR f.origin_visibility_mi < 1
                   THEN 'Fog / low visibility'
               WHEN f.origin_present_weather LIKE '%RA%' OR f.origin_present_weather LIKE '%DZ%'
                   THEN 'Rain'
               WHEN f.origin_wind_speed_mph >= 25 OR f.origin_wind_gust_mph >= 35 THEN 'High wind'
               ELSE 'Clear / other'
           END AS origin_condition
) AS c
GROUP BY f.month_key, c.origin_condition;
