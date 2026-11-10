-- Grain: flight x delay cause. Only flights with arrival delay >= 15 minutes (BTS rule).
CREATE TABLE dbo.fact_flight_delay_causes (
    flight_id     BIGINT      NOT NULL,
    cause_code    VARCHAR(20) NOT NULL,
    delay_minutes INT         NOT NULL,
    CONSTRAINT pk_fact_flight_delay_causes PRIMARY KEY (flight_id, cause_code),
    CONSTRAINT fk_ffdc_flight FOREIGN KEY (flight_id) REFERENCES dbo.fact_flights (flight_id),
    CONSTRAINT fk_ffdc_cause FOREIGN KEY (cause_code) REFERENCES dbo.dim_delay_causes (cause_code),
    CONSTRAINT ck_ffdc_minutes CHECK (delay_minutes >= 0)
);
