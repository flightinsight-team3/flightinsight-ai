-- Local calendar date. Populated by the ETL (holidays generated in Python).
CREATE TABLE dbo.dim_date (
    date_key                INT          NOT NULL,  -- yyyymmdd
    full_date               DATE         NOT NULL,
    year                    SMALLINT     NOT NULL,
    quarter                 TINYINT      NOT NULL,
    month                   TINYINT      NOT NULL,
    day_of_week             TINYINT      NOT NULL,  -- 1 = Monday ... 7 = Sunday
    is_weekend              BIT          NOT NULL,
    is_holiday              BIT          NOT NULL,
    holiday_name            VARCHAR(50)  NULL,
    days_to_nearest_holiday INT          NULL,
    season                  VARCHAR(10)  NOT NULL,
    CONSTRAINT pk_dim_date PRIMARY KEY (date_key),
    CONSTRAINT uq_dim_date_full_date UNIQUE (full_date)
);
