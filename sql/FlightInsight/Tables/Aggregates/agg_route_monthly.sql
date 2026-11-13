-- Grain: route x airline x month. Source for Cosmos route_summaries and Gremlin route edges.
CREATE TABLE dbo.agg_route_monthly (
    route_key           INT           NOT NULL,
    airline_key         INT           NOT NULL,
    month_key           INT           NOT NULL,  -- yyyymm
    flights             INT           NOT NULL,
    cancelled           INT           NOT NULL,
    diverted            INT           NOT NULL,
    on_time_rate        DECIMAL(5, 4) NULL,
    avg_arr_delay_min   DECIMAL(7, 2) NULL,
    p90_arr_delay_min   DECIMAL(7, 2) NULL,
    weather_delay_share DECIMAL(5, 4) NULL,
    CONSTRAINT pk_agg_route_monthly PRIMARY KEY (route_key, airline_key, month_key),
    CONSTRAINT fk_arm_route FOREIGN KEY (route_key) REFERENCES dbo.dim_routes (route_key),
    CONSTRAINT fk_arm_airline FOREIGN KEY (airline_key) REFERENCES dbo.dim_airlines (airline_key),
    CONSTRAINT ck_arm_month_key CHECK (month_key BETWEEN 200001 AND 210012 AND month_key % 100 BETWEEN 1 AND 12)
);
