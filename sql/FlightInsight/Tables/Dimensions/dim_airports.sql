CREATE TABLE dbo.dim_airports (
    airport_key   INT IDENTITY(1, 1) NOT NULL,
    iata_code     CHAR(3)            NOT NULL,
    icao_code     CHAR(4)            NULL,
    airport_name  VARCHAR(200)       NOT NULL,
    city          VARCHAR(100)       NULL,
    geo_key       INT                NULL,
    latitude      DECIMAL(9, 6)      NULL,
    longitude     DECIMAL(9, 6)      NULL,
    timezone      VARCHAR(50)        NOT NULL,  -- IANA name, e.g. America/New_York (used for UTC conversion)
    hub_type      VARCHAR(20)        NULL,      -- large / medium / small
    is_top30      BIT                NOT NULL CONSTRAINT df_dim_airports_is_top30 DEFAULT (0),
    CONSTRAINT pk_dim_airports PRIMARY KEY (airport_key),
    CONSTRAINT uq_dim_airports_iata UNIQUE (iata_code),
    CONSTRAINT fk_dim_airports_geography FOREIGN KEY (geo_key) REFERENCES dbo.dim_geography (geo_key)
);
