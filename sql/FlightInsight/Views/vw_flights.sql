-- One row per flight with readable names, calendar attributes and the matched origin/destination weather.
-- Defines the shared measures used by every other view:
--   is_completed = not cancelled, not diverted, arrival delay known
--   is_on_time   = completed and arriving less than 15 minutes late (BTS definition)
CREATE VIEW dbo.vw_flights
AS
SELECT f.flight_id,
       f.date_key,
       f.date_key / 100 AS month_key,
       d.full_date,
       d.year,
       d.month,
       d.day_of_week,
       d.is_weekend,
       d.is_holiday,
       d.holiday_name,
       d.days_to_nearest_holiday,
       d.season,
       f.dep_local_hour_key AS dep_local_hour,
       h.time_band,
       a.carrier_code,
       a.airline_name,
       f.flight_number,
       f.tail_number,
       r.route_key,
       o.iata_code AS origin,
       o.airport_name AS origin_airport_name,
       o.city AS origin_city,
       og.state_code AS origin_state,
       de.iata_code AS dest,
       de.airport_name AS dest_airport_name,
       de.city AS dest_city,
       dg.state_code AS dest_state,
       r.distance_mi,
       f.sched_dep_local,
       f.sched_dep_utc,
       f.actual_dep_utc,
       f.sched_arr_utc,
       f.actual_arr_utc,
       f.dep_delay_min,
       f.arr_delay_min,
       f.taxi_out_min,
       f.taxi_in_min,
       CAST(f.is_cancelled AS INT) AS is_cancelled,
       f.cancellation_code,
       cr.reason_name AS cancellation_reason,
       CAST(f.is_diverted AS INT) AS is_diverted,
       m.is_completed,
       CASE WHEN m.is_completed = 1 AND f.arr_delay_min < 15 THEN 1 ELSE 0 END AS is_on_time,
       ow.temperature_f AS origin_temperature_f,
       ow.precipitation_in AS origin_precipitation_in,
       ow.wind_speed_mph AS origin_wind_speed_mph,
       ow.wind_gust_mph AS origin_wind_gust_mph,
       ow.visibility_mi AS origin_visibility_mi,
       ow.present_weather AS origin_present_weather,
       CAST(ow.is_adverse AS INT) AS origin_is_adverse,
       dw.temperature_f AS dest_temperature_f,
       dw.precipitation_in AS dest_precipitation_in,
       dw.wind_speed_mph AS dest_wind_speed_mph,
       dw.wind_gust_mph AS dest_wind_gust_mph,
       dw.visibility_mi AS dest_visibility_mi,
       dw.present_weather AS dest_present_weather,
       CAST(dw.is_adverse AS INT) AS dest_is_adverse
FROM dbo.fact_flights AS f
JOIN dbo.dim_date AS d ON d.date_key = f.date_key
JOIN dbo.dim_hour AS h ON h.hour_key = f.dep_local_hour_key
JOIN dbo.dim_airlines AS a ON a.airline_key = f.airline_key
JOIN dbo.dim_routes AS r ON r.route_key = f.route_key
JOIN dbo.dim_airports AS o ON o.airport_key = r.origin_airport_key
JOIN dbo.dim_airports AS de ON de.airport_key = r.dest_airport_key
LEFT JOIN dbo.dim_geography AS og ON og.geo_key = o.geo_key
LEFT JOIN dbo.dim_geography AS dg ON dg.geo_key = de.geo_key
LEFT JOIN dbo.dim_cancellation_reasons AS cr ON cr.cancellation_code = f.cancellation_code
LEFT JOIN dbo.fact_flight_weather AS w ON w.flight_id = f.flight_id
LEFT JOIN dbo.fact_weather_hourly AS ow
  ON ow.station_key = w.origin_station_key AND ow.obs_hour_utc = w.origin_obs_hour_utc
LEFT JOIN dbo.fact_weather_hourly AS dw
  ON dw.station_key = w.dest_station_key AND dw.obs_hour_utc = w.dest_obs_hour_utc
CROSS APPLY (
    SELECT CASE WHEN f.is_cancelled = 0 AND f.is_diverted = 0 AND f.arr_delay_min IS NOT NULL
                THEN 1 ELSE 0 END AS is_completed
) AS m;
