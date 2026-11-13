-- The five BTS delay-cause categories. Seeded by Scripts/PostDeployment.sql.
CREATE TABLE dbo.dim_delay_causes (
    cause_code VARCHAR(20) NOT NULL,
    cause_name VARCHAR(50) NOT NULL,
    CONSTRAINT pk_dim_delay_causes PRIMARY KEY (cause_code)
);
