-- Local departure hour 0-23. Seeded by Scripts/PostDeployment.sql.
CREATE TABLE dbo.dim_hour (
    hour_key  TINYINT     NOT NULL,
    time_band VARCHAR(20) NOT NULL,
    CONSTRAINT pk_dim_hour PRIMARY KEY (hour_key),
    CONSTRAINT ck_dim_hour_range CHECK (hour_key BETWEEN 0 AND 23)
);
