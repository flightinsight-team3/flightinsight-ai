-- Loads one month from staging into the star schema in dependency order, as one transaction.
-- Called by the ADF pipeline PL_Load_Star_Month after the source pipelines have filled stg_*.
-- Safe to re-run: every step upserts or deletes-and-reloads the month.
CREATE PROCEDURE dbo.usp_load_month
    @month_key INT,
    @run_id    VARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @load_id BIGINT;
    DECLARE @rows_read INT = (SELECT COUNT(*) FROM dbo.stg_flights WHERE month_key = @month_key);

    INSERT INTO dbo.etl_load_log (run_id, source, month_key, step, status, rows_read)
    VALUES (@run_id, 'star_schema', @month_key, 'usp_load_month', 'started', @rows_read);
    SET @load_id = SCOPE_IDENTITY();

    BEGIN TRY
        BEGIN TRANSACTION;

        EXEC dbo.usp_load_dim_geography;
        EXEC dbo.usp_load_dim_airports;
        EXEC dbo.usp_load_dim_weather_stations;
        EXEC dbo.usp_load_bridge_airport_station;
        EXEC dbo.usp_load_dim_date @month_key = @month_key;
        EXEC dbo.usp_load_dim_airlines @month_key = @month_key;
        EXEC dbo.usp_load_dim_routes @month_key = @month_key;
        EXEC dbo.usp_load_fact_weather @month_key = @month_key;
        EXEC dbo.usp_load_fact_flights @month_key = @month_key;
        EXEC dbo.usp_load_fact_flight_weather @month_key = @month_key;
        EXEC dbo.usp_load_agg_route_monthly @month_key = @month_key;

        COMMIT TRANSACTION;

        DECLARE @rows_loaded INT = (
            SELECT COUNT(*) FROM dbo.fact_flights
            WHERE date_key BETWEEN @month_key * 100 + 1 AND @month_key * 100 + 31);

        UPDATE dbo.etl_load_log
        SET status = 'succeeded',
            rows_loaded = @rows_loaded,
            rows_rejected = @rows_read - @rows_loaded,
            message = CASE WHEN @rows_read > @rows_loaded
                           THEN 'rows_rejected = flights whose airline or airports are not in the dimensions'
                      END,
            finished_at = SYSUTCDATETIME()
        WHERE load_id = @load_id;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        UPDATE dbo.etl_load_log
        SET status = 'failed',
            message = LEFT(ERROR_MESSAGE(), 4000),
            finished_at = SYSUTCDATETIME()
        WHERE load_id = @load_id;

        THROW;
    END CATCH;
END;
