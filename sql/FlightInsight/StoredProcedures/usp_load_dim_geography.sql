-- Upserts dim_geography from the latest stg_geography snapshot. Keys are stable across reloads.
CREATE PROCEDURE dbo.usp_load_dim_geography
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @snapshot_key INT = (SELECT MAX(snapshot_key) FROM dbo.stg_geography);

    MERGE dbo.dim_geography AS t
    USING (
        SELECT state_code, state_name, state_fips, census_region
        FROM dbo.stg_geography
        WHERE snapshot_key = @snapshot_key
    ) AS s
    ON t.state_code = s.state_code
    WHEN MATCHED THEN UPDATE SET
        state_name    = s.state_name,
        state_fips    = s.state_fips,
        census_region = s.census_region
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (state_code, state_name, state_fips, census_region)
        VALUES (s.state_code, s.state_name, s.state_fips, s.census_region);
END;
