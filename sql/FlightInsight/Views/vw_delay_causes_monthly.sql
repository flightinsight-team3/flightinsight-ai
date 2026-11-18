-- Month x airline x delay cause: minutes attributed to each BTS cause and its share of the airline's total.
-- Only flights arriving 15+ minutes late carry causes.
CREATE VIEW dbo.vw_delay_causes_monthly
AS
SELECT f.date_key / 100 AS month_key,
       a.carrier_code,
       a.airline_name,
       c.cause_code,
       dc.cause_name,
       COUNT(*) AS flights_affected,
       SUM(c.delay_minutes) AS delay_minutes,
       CAST(1.0 * SUM(c.delay_minutes)
            / NULLIF(SUM(SUM(c.delay_minutes)) OVER (PARTITION BY f.date_key / 100, a.carrier_code), 0)
            AS DECIMAL(5, 4)) AS share_of_airline_minutes
FROM dbo.fact_flight_delay_causes AS c
JOIN dbo.fact_flights AS f ON f.flight_id = c.flight_id
JOIN dbo.dim_airlines AS a ON a.airline_key = f.airline_key
JOIN dbo.dim_delay_causes AS dc ON dc.cause_code = c.cause_code
WHERE c.delay_minutes > 0
GROUP BY f.date_key / 100, a.carrier_code, a.airline_name, c.cause_code, dc.cause_name;
