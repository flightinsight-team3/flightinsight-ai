-- One row per calendar day: daily performance next to weekday, holiday and season attributes.
CREATE VIEW dbo.vw_delay_by_date
AS
SELECT date_key,
       full_date,
       month_key,
       day_of_week,
       is_weekend,
       is_holiday,
       holiday_name,
       days_to_nearest_holiday,
       season,
       COUNT(*) AS flights,
       SUM(is_cancelled) AS cancelled,
       CAST(1.0 * SUM(is_cancelled) / COUNT(*) AS DECIMAL(5, 4)) AS cancel_rate,
       CAST(1.0 * SUM(is_on_time) / NULLIF(SUM(is_completed), 0) AS DECIMAL(5, 4)) AS on_time_rate,
       CAST(AVG(CASE WHEN is_completed = 1 THEN 1.0 * arr_delay_min END) AS DECIMAL(7, 2))
           AS avg_arr_delay_min
FROM dbo.vw_flights
GROUP BY date_key, full_date, month_key, day_of_week, is_weekend, is_holiday, holiday_name,
         days_to_nearest_holiday, season;
