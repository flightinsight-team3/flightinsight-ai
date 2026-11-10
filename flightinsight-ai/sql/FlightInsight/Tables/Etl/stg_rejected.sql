-- Rows that failed data-quality checks, kept for inspection instead of being silently dropped.
CREATE TABLE dbo.stg_rejected (
    rejected_id BIGINT IDENTITY(1, 1) NOT NULL,
    load_id     BIGINT         NULL,
    source      VARCHAR(30)    NOT NULL,
    month_key   INT            NULL,
    reason      VARCHAR(200)   NOT NULL,
    raw_record  NVARCHAR(MAX)  NULL,  -- original row as JSON
    rejected_at DATETIME2(0)   NOT NULL CONSTRAINT df_stg_rejected_at DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT pk_stg_rejected PRIMARY KEY (rejected_id),
    CONSTRAINT fk_stg_rejected_load FOREIGN KEY (load_id) REFERENCES dbo.etl_load_log (load_id)
);
