-- Airline x month performance: volume, cancellations, on-time rate and average delays.
CREATE VIEW dbo.vw_airline_monthly
AS
SELECT month_key,
       carrier_code,
       airline_name,
       COUNT(*) AS flights,
       SUM(is_cancelled) AS cancelled,
       SUM(is_diverted) AS diverted,
       CAST(1.0 * SUM(is_cancelled) / COUNT(*) AS DECIMAL(5, 4)) AS cancel_rate,
       CAST(1.0 * SUM(is_on_time) / NULLIF(SUM(is_completed), 0) AS DECIMAL(5, 4)) AS on_time_rate,
       CAST(AVG(CASE WHEN is_completed = 1 THEN 1.0 * arr_delay_min END) AS DECIMAL(7, 2))
           AS avg_arr_delay_min,
       CAST(AVG(CASE WHEN is_cancelled = 0 THEN 1.0 * dep_delay_min END) AS DECIMAL(7, 2))
           AS avg_dep_delay_min
FROM dbo.vw_flights
GROUP BY month_key, carrier_code, airline_name;
