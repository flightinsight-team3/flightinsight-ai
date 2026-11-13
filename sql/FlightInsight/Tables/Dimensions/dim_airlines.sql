CREATE TABLE dbo.dim_airlines (
    airline_key    INT IDENTITY(1, 1) NOT NULL,
    dot_airline_id INT                NOT NULL,
    carrier_code   VARCHAR(3)         NOT NULL,
    airline_name   VARCHAR(100)       NOT NULL,
    CONSTRAINT pk_dim_airlines PRIMARY KEY (airline_key),
    CONSTRAINT uq_dim_airlines_dot_id UNIQUE (dot_airline_id)
);
