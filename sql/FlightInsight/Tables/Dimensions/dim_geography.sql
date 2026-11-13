CREATE TABLE dbo.dim_geography (
    geo_key        INT IDENTITY(1, 1) NOT NULL,
    state_code     CHAR(2)            NOT NULL,
    state_name     VARCHAR(50)        NOT NULL,
    state_fips     CHAR(2)            NULL,
    census_region  VARCHAR(20)        NULL,
    CONSTRAINT pk_dim_geography PRIMARY KEY (geo_key),
    CONSTRAINT uq_dim_geography_state UNIQUE (state_code)
);
