-- Staging for BTS flights: one row per in-scope flight, exactly the columns of
-- clean/bts/<yyyymm>/flights.parquet (see functions/etl/bts.py STG_COLUMNS).
-- Loaded by an ADF Copy activity; each month is deleted and reloaded as a unit.
-- No foreign keys here: staging holds codes; stored procedures resolve them to keys.
CREATE TABLE dbo.stg_flights (
    month_key               INT          NOT NULL,
    date_key                INT          NOT NULL,
    carrier_code            VARCHAR(3)   NOT NULL,
    dot_airline_id          INT          NOT NULL,
    flight_number           VARCHAR(10)  NOT NULL,
    tail_number             VARCHAR(10)  NULL,
    origin                  CHAR(3)      NOT NULL,
    origin_state            CHAR(2)      NULL,
    dest                    CHAR(3)      NOT NULL,
    dest_state              CHAR(2)      NULL,
    distance_mi             INT          NULL,
    sched_dep_local         DATETIME2(0) NOT NULL,
    dep_local_hour          TINYINT      NOT NULL,
    sched_dep_utc           DATETIME2(0) NOT NULL,
    actual_dep_utc          DATETIME2(0) NULL,
    sched_arr_utc           DATETIME2(0) NOT NULL,
    actual_arr_utc          DATETIME2(0) NULL,
    crs_elapsed_min         INT          NOT NULL,
    dep_delay_min           INT          NULL,
    arr_delay_min           INT          NULL,
    taxi_out_min            INT          NULL,
    taxi_in_min             INT          NULL,
    is_cancelled            BIT          NOT NULL,
    cancellation_code       CHAR(1)      NULL,
    is_diverted             BIT          NOT NULL,
    carrier_delay_min       INT          NULL,
    weather_delay_min       INT          NULL,
    nas_delay_min           INT          NULL,
    security_delay_min      INT          NULL,
    late_aircraft_delay_min INT          NULL
);
GO

CREATE INDEX ix_stg_flights_month ON dbo.stg_flights (month_key);
