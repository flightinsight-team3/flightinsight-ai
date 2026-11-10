/*
Post-deployment script: runs after every schema deployment. Must be idempotent (safe to re-run),
so every statement uses MERGE. Only small, fixed reference data belongs here; real data comes from ETL.
*/

MERGE dbo.dim_cancellation_reasons AS t
USING (VALUES
    ('A', 'Carrier'),
    ('B', 'Weather'),
    ('C', 'National Air System'),
    ('D', 'Security')
) AS s (cancellation_code, reason_name)
ON t.cancellation_code = s.cancellation_code
WHEN MATCHED AND t.reason_name <> s.reason_name THEN UPDATE SET reason_name = s.reason_name
WHEN NOT MATCHED THEN INSERT (cancellation_code, reason_name) VALUES (s.cancellation_code, s.reason_name);
GO

MERGE dbo.dim_delay_causes AS t
USING (VALUES
    ('carrier', 'Carrier delay'),
    ('weather', 'Weather delay'),
    ('nas', 'National Air System delay'),
    ('security', 'Security delay'),
    ('late_aircraft', 'Late-arriving aircraft delay')
) AS s (cause_code, cause_name)
ON t.cause_code = s.cause_code
WHEN MATCHED AND t.cause_name <> s.cause_name THEN UPDATE SET cause_name = s.cause_name
WHEN NOT MATCHED THEN INSERT (cause_code, cause_name) VALUES (s.cause_code, s.cause_name);
GO

WITH hours AS (
    SELECT TOP (24) CAST(ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS TINYINT) AS hour_key
    FROM sys.all_objects
)
MERGE dbo.dim_hour AS t
USING (
    SELECT hour_key,
           CASE
               WHEN hour_key BETWEEN 5 AND 8 THEN 'Early morning'
               WHEN hour_key BETWEEN 9 AND 11 THEN 'Morning'
               WHEN hour_key BETWEEN 12 AND 16 THEN 'Afternoon'
               WHEN hour_key BETWEEN 17 AND 20 THEN 'Evening'
               ELSE 'Night'
           END AS time_band
    FROM hours
) AS s
ON t.hour_key = s.hour_key
WHEN MATCHED AND t.time_band <> s.time_band THEN UPDATE SET time_band = s.time_band
WHEN NOT MATCHED THEN INSERT (hour_key, time_band) VALUES (s.hour_key, s.time_band);
GO
