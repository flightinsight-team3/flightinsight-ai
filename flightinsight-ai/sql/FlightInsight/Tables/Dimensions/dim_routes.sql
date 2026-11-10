-- One row per directed airport pair. Shared key with Cosmos route_summaries and Gremlin route edges.
CREATE TABLE dbo.dim_routes (
    route_key          INT IDENTITY(1, 1) NOT NULL,
    origin_airport_key INT                NOT NULL,
    dest_airport_key   INT                NOT NULL,
    distance_mi        INT                NULL,
    CONSTRAINT pk_dim_routes PRIMARY KEY (route_key),
    CONSTRAINT uq_dim_routes_pair UNIQUE (origin_airport_key, dest_airport_key),
    CONSTRAINT fk_dim_routes_origin FOREIGN KEY (origin_airport_key) REFERENCES dbo.dim_airports (airport_key),
    CONSTRAINT fk_dim_routes_dest FOREIGN KEY (dest_airport_key) REFERENCES dbo.dim_airports (airport_key),
    CONSTRAINT ck_dim_routes_distinct CHECK (origin_airport_key <> dest_airport_key)
);
