-- Deletes and reloads fact_flights and fact_flight_delay_causes for @month_key.
-- Run after usp_load_dim_date, usp_load_dim_airlines and usp_load_dim_routes.
-- Delay causes are only recorded for flights arriving 15+ minutes late (BTS reporting rule).
CREATE PROCEDURE dbo.usp_load_fact_flights
    @month_key INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @first_date_key INT = @month_key * 100 + 1;
    DECLARE @last_date_key INT = @month_key * 100 + 31;

    DELETE c
    FROM dbo.fact_flight_delay_causes AS c
    JOIN dbo.fact_flights AS f ON f.flight_id = c.flight_id
    WHERE f.date_key BETWEEN @first_date_key AND @last_date_key;

    DELETE w
    FROM dbo.fact_flight_weather AS w
    JOIN dbo.fact_flights AS f ON f.flight_id = w.flight_id
    WHERE f.date_key BETWEEN @first_date_key AND @last_date_key;

    DELETE FROM dbo.fact_flights
    WHERE date_key BETWEEN @first_date_key AND @last_date_key;

    INSERT INTO dbo.fact_flights (
        date_key, dep_local_hour_key, airline_key, route_key, cancellation_code,
        flight_number, tail_number, sched_dep_local, sched_dep_utc, actual_dep_utc,
        sched_arr_utc, actual_arr_utc, dep_delay_min, arr_delay_min,
        taxi_out_min, taxi_in_min, is_cancelled, is_diverted)
    SELECT s.date_key, s.dep_local_hour, a.airline_key, r.route_key, s.cancellation_code,
           s.flight_number, s.tail_number, s.sched_dep_local, s.sched_dep_utc, s.actual_dep_utc,
           s.sched_arr_utc, s.actual_arr_utc, s.dep_delay_min, s.arr_delay_min,
           s.taxi_out_min, s.taxi_in_min, s.is_cancelled, s.is_diverted
    FROM dbo.stg_flights AS s
    JOIN dbo.dim_airlines AS a ON a.dot_airline_id = s.dot_airline_id
    JOIN dbo.dim_airports AS o ON o.iata_code = s.origin
    JOIN dbo.dim_airports AS d ON d.iata_code = s.dest
    JOIN dbo.dim_routes AS r
      ON r.origin_airport_key = o.airport_key AND r.dest_airport_key = d.airport_key
    WHERE s.month_key = @month_key;

    INSERT INTO dbo.fact_flight_delay_causes (flight_id, cause_code, delay_minutes)
    SELECT f.flight_id, v.cause_code, v.delay_minutes
    FROM dbo.stg_flights AS s
    JOIN dbo.dim_airlines AS a ON a.dot_airline_id = s.dot_airline_id
    JOIN dbo.dim_airports AS o ON o.iata_code = s.origin
    JOIN dbo.dim_airports AS d ON d.iata_code = s.dest
    JOIN dbo.dim_routes AS r
      ON r.origin_airport_key = o.airport_key AND r.dest_airport_key = d.airport_key
    JOIN dbo.fact_flights AS f
      ON f.date_key = s.date_key
     AND f.airline_key = a.airline_key
     AND f.flight_number = s.flight_number
     AND f.route_key = r.route_key
     AND f.sched_dep_local = s.sched_dep_local
    CROSS APPLY (VALUES
        ('carrier', s.carrier_delay_min),
        ('weather', s.weather_delay_min),
        ('nas', s.nas_delay_min),
        ('security', s.security_delay_min),
        ('late_aircraft', s.late_aircraft_delay_min)
    ) AS v (cause_code, delay_minutes)
    WHERE s.month_key = @month_key
      AND s.arr_delay_min >= 15
      AND v.delay_minutes IS NOT NULL
      AND v.delay_minutes >= 0;
END;
