-- One row per ETL step per run. ADF passes its run id so runs can be traced end to end.
CREATE TABLE dbo.etl_load_log (
    load_id       BIGINT IDENTITY(1, 1) NOT NULL,
    run_id        VARCHAR(100)   NULL,
    source        VARCHAR(30)    NOT NULL,  -- bts / noaa / airports / asrs / ...
    month_key     INT            NULL,
    step          VARCHAR(50)    NOT NULL,
    status        VARCHAR(20)    NOT NULL,
    rows_read     INT            NULL,
    rows_loaded   INT            NULL,
    rows_rejected INT            NULL,
    message       NVARCHAR(4000) NULL,
    started_at    DATETIME2(0)   NOT NULL CONSTRAINT df_etl_load_log_started DEFAULT (SYSUTCDATETIME()),
    finished_at   DATETIME2(0)   NULL,
    CONSTRAINT pk_etl_load_log PRIMARY KEY (load_id),
    CONSTRAINT ck_etl_load_log_status CHECK (status IN ('started', 'succeeded', 'failed'))
);
