-- Grain: one row per flight. Timestamps in UTC except sched_dep_local / date_key / dep_local_hour_key.
CREATE TABLE dbo.fact_flights (
    flight_id          BIGINT IDENTITY(1, 1) NOT NULL,
    date_key           INT          NOT NULL,
    dep_local_hour_key TINYINT      NOT NULL,
    airline_key        INT          NOT NULL,
    route_key          INT          NOT NULL,
    cancellation_code  CHAR(1)      NULL,
    flight_number      VARCHAR(10)  NOT NULL,
    tail_number        VARCHAR(10)  NULL,
    sched_dep_local    DATETIME2(0) NOT NULL,
    sched_dep_utc      DATETIME2(0) NOT NULL,
    actual_dep_utc     DATETIME2(0) NULL,
    sched_arr_utc      DATETIME2(0) NOT NULL,
    actual_arr_utc     DATETIME2(0) NULL,
    dep_delay_min      INT          NULL,
    arr_delay_min      INT          NULL,
    taxi_out_min       INT          NULL,
    taxi_in_min        INT          NULL,
    is_cancelled       BIT          NOT NULL,
    is_diverted        BIT          NOT NULL,
    CONSTRAINT pk_fact_flights PRIMARY KEY (flight_id),
    -- Natural key from BTS; makes month-level delete-and-reload safe against duplicates.
    CONSTRAINT uq_fact_flights_natural UNIQUE (date_key, airline_key, flight_number, route_key, sched_dep_local),
    CONSTRAINT fk_fact_flights_date FOREIGN KEY (date_key) REFERENCES dbo.dim_date (date_key),
    CONSTRAINT fk_fact_flights_hour FOREIGN KEY (dep_local_hour_key) REFERENCES dbo.dim_hour (hour_key),
    CONSTRAINT fk_fact_flights_airline FOREIGN KEY (airline_key) REFERENCES dbo.dim_airlines (airline_key),
    CONSTRAINT fk_fact_flights_route FOREIGN KEY (route_key) REFERENCES dbo.dim_routes (route_key),
    CONSTRAINT fk_fact_flights_cancellation FOREIGN KEY (cancellation_code) REFERENCES dbo.dim_cancellation_reasons (cancellation_code)
);
GO

CREATE INDEX ix_fact_flights_route_date ON dbo.fact_flights (route_key, date_key);
GO

CREATE INDEX ix_fact_flights_airline_date ON dbo.fact_flights (airline_key, date_key);
