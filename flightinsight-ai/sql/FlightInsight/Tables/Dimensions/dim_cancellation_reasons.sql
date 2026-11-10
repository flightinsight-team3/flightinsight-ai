-- BTS cancellation codes A-D. Seeded by Scripts/PostDeployment.sql.
CREATE TABLE dbo.dim_cancellation_reasons (
    cancellation_code CHAR(1)     NOT NULL,
    reason_name       VARCHAR(50) NOT NULL,
    CONSTRAINT pk_dim_cancellation_reasons PRIMARY KEY (cancellation_code)
);
