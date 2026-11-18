-- Deletes and reloads fact_weather_hourly and fact_weather_daily for the local days of @month_key.
-- Run after usp_load_dim_weather_stations and usp_load_dim_date. Flight links into the replaced
-- hours are cleared first; usp_load_fact_flight_weather rebuilds them for the month being loaded.
CREATE PROCEDURE dbo.usp_load_fact_weather
    @month_key INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @first_date_key INT = @month_key * 100 + 1;
    DECLARE @last_date_key INT = @month_key * 100 + 31;

    UPDATE w SET origin_obs_hour_utc = NULL, origin_time_gap_min = NULL
    FROM dbo.fact_flight_weather AS w
    JOIN dbo.fact_weather_hourly AS h
      ON h.station_key = w.origin_station_key AND h.obs_hour_utc = w.origin_obs_hour_utc
    WHERE h.local_date_key BETWEEN @first_date_key AND @last_date_key;

    UPDATE w SET dest_obs_hour_utc = NULL, dest_time_gap_min = NULL
    FROM dbo.fact_flight_weather AS w
    JOIN dbo.fact_weather_hourly AS h
      ON h.station_key = w.dest_station_key AND h.obs_hour_utc = w.dest_obs_hour_utc
    WHERE h.local_date_key BETWEEN @first_date_key AND @last_date_key;

    DELETE FROM dbo.fact_weather_hourly
    WHERE local_date_key BETWEEN @first_date_key AND @last_date_key;

    INSERT INTO dbo.fact_weather_hourly (
        station_key, obs_hour_utc, local_date_key, temperature_f, precipitation_in,
        is_trace_precip, wind_speed_mph, wind_gust_mph, visibility_mi, present_weather, is_adverse)
    SELECT st.station_key, h.obs_hour_utc, h.local_date_key, h.temperature_f, h.precipitation_in,
           h.is_trace_precip, h.wind_speed_mph, h.wind_gust_mph, h.visibility_mi,
           h.present_weather, h.is_adverse
    FROM dbo.stg_weather_hourly AS h
    JOIN dbo.dim_weather_stations AS st ON st.station_id = h.station_id
    WHERE h.month_key = @month_key;

    DELETE FROM dbo.fact_weather_daily
    WHERE date_key BETWEEN @first_date_key AND @last_date_key;

    INSERT INTO dbo.fact_weather_daily (
        station_key, date_key, snowfall_in, snow_depth_in, precipitation_in)
    SELECT st.station_key, d.date_key, d.snowfall_in, d.snow_depth_in, d.precipitation_in
    FROM dbo.stg_weather_daily AS d
    JOIN dbo.dim_weather_stations AS st ON st.station_id = d.station_id
    WHERE d.month_key = @month_key;
END;
