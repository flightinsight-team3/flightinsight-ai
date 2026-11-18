-- Upserts every calendar day of @month_key into dim_date, with US federal holidays.
-- Holidays of the neighbouring years are generated too so days_to_nearest_holiday is right at year edges.
CREATE PROCEDURE dbo.usp_load_dim_date
    @month_key INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @first DATE = DATEFROMPARTS(@month_key / 100, @month_key % 100, 1);
    DECLARE @last DATE = EOMONTH(@first);
    DECLARE @year INT = @month_key / 100;

    WITH years AS (
        SELECT y FROM (VALUES (@year - 1), (@year), (@year + 1)) AS v (y)
    ),
    month_starts AS (
        -- wd: weekday of the 1st, 1 = Monday ... 7 = Sunday
        SELECT y.y, m.m, f.f, DATEDIFF(DAY, '19000101', f.f) % 7 + 1 AS wd
        FROM years AS y
        CROSS JOIN (VALUES (1), (2), (5), (9), (10), (11)) AS m (m)
        CROSS APPLY (SELECT DATEFROMPARTS(y.y, m.m, 1) AS f) AS f
    ),
    holidays AS (
        SELECT DATEFROMPARTS(y, 1, 1) AS d, 'New Year''s Day' AS name FROM years
        UNION ALL SELECT DATEFROMPARTS(y, 6, 19), 'Juneteenth' FROM years
        UNION ALL SELECT DATEFROMPARTS(y, 7, 4), 'Independence Day' FROM years
        UNION ALL SELECT DATEFROMPARTS(y, 11, 11), 'Veterans Day' FROM years
        UNION ALL SELECT DATEFROMPARTS(y, 12, 25), 'Christmas Day' FROM years
        UNION ALL SELECT DATEADD(DAY, (8 - wd) % 7 + 14, f), 'Martin Luther King Jr. Day'
                  FROM month_starts WHERE m = 1
        UNION ALL SELECT DATEADD(DAY, (8 - wd) % 7 + 14, f), 'Presidents Day'
                  FROM month_starts WHERE m = 2
        UNION ALL SELECT DATEADD(DAY, -(DATEDIFF(DAY, '19000101', EOMONTH(f)) % 7), EOMONTH(f)),
                         'Memorial Day'
                  FROM month_starts WHERE m = 5
        UNION ALL SELECT DATEADD(DAY, (8 - wd) % 7, f), 'Labor Day'
                  FROM month_starts WHERE m = 9
        UNION ALL SELECT DATEADD(DAY, (8 - wd) % 7 + 7, f), 'Columbus Day'
                  FROM month_starts WHERE m = 10
        UNION ALL SELECT DATEADD(DAY, (11 - wd) % 7 + 21, f), 'Thanksgiving Day'
                  FROM month_starts WHERE m = 11
    ),
    days AS (
        SELECT DATEADD(DAY, tens.n * 10 + ones.n, @first) AS d
        FROM (VALUES (0), (1), (2), (3)) AS tens (n)
        CROSS JOIN (VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8), (9)) AS ones (n)
        WHERE tens.n * 10 + ones.n <= DATEDIFF(DAY, @first, @last)
    )
    MERGE dbo.dim_date AS t
    USING (
        SELECT YEAR(days.d) * 10000 + MONTH(days.d) * 100 + DAY(days.d) AS date_key,
               days.d AS full_date,
               YEAR(days.d) AS year,
               DATEPART(QUARTER, days.d) AS quarter,
               MONTH(days.d) AS month,
               w.day_of_week,
               CASE WHEN w.day_of_week IN (6, 7) THEN 1 ELSE 0 END AS is_weekend,
               CASE WHEN h.d IS NULL THEN 0 ELSE 1 END AS is_holiday,
               h.name AS holiday_name,
               (SELECT TOP (1) ABS(DATEDIFF(DAY, days.d, h2.d))
                FROM holidays AS h2
                ORDER BY ABS(DATEDIFF(DAY, days.d, h2.d))) AS days_to_nearest_holiday,
               CASE
                   WHEN MONTH(days.d) IN (12, 1, 2) THEN 'Winter'
                   WHEN MONTH(days.d) IN (3, 4, 5) THEN 'Spring'
                   WHEN MONTH(days.d) IN (6, 7, 8) THEN 'Summer'
                   ELSE 'Fall'
               END AS season
        FROM days
        CROSS APPLY (SELECT DATEDIFF(DAY, '19000101', days.d) % 7 + 1 AS day_of_week) AS w
        LEFT JOIN holidays AS h ON h.d = days.d
    ) AS s
    ON t.date_key = s.date_key
    WHEN MATCHED THEN UPDATE SET
        full_date               = s.full_date,
        year                    = s.year,
        quarter                 = s.quarter,
        month                   = s.month,
        day_of_week             = s.day_of_week,
        is_weekend              = s.is_weekend,
        is_holiday              = s.is_holiday,
        holiday_name            = s.holiday_name,
        days_to_nearest_holiday = s.days_to_nearest_holiday,
        season                  = s.season
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (date_key, full_date, year, quarter, month, day_of_week, is_weekend,
                is_holiday, holiday_name, days_to_nearest_holiday, season)
        VALUES (s.date_key, s.full_date, s.year, s.quarter, s.month, s.day_of_week, s.is_weekend,
                s.is_holiday, s.holiday_name, s.days_to_nearest_holiday, s.season);
END;
