-- Upserts the carriers seen in stg_flights for @month_key. BTS on-time data has no carrier names,
-- so names come from a fixed lookup of reporting carriers; unknown carriers fall back to their code.
CREATE PROCEDURE dbo.usp_load_dim_airlines
    @month_key INT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    WITH names AS (
        SELECT carrier_code, airline_name
        FROM (VALUES
            ('9E', 'Endeavor Air'),
            ('AA', 'American Airlines'),
            ('AS', 'Alaska Airlines'),
            ('B6', 'JetBlue Airways'),
            ('DL', 'Delta Air Lines'),
            ('F9', 'Frontier Airlines'),
            ('G4', 'Allegiant Air'),
            ('HA', 'Hawaiian Airlines'),
            ('MQ', 'Envoy Air'),
            ('NK', 'Spirit Air Lines'),
            ('OH', 'PSA Airlines'),
            ('OO', 'SkyWest Airlines'),
            ('UA', 'United Air Lines'),
            ('WN', 'Southwest Airlines'),
            ('YX', 'Republic Airline')
        ) AS v (carrier_code, airline_name)
    ),
    carriers AS (
        SELECT dot_airline_id, MAX(carrier_code) AS carrier_code
        FROM dbo.stg_flights
        WHERE month_key = @month_key
        GROUP BY dot_airline_id
    )
    MERGE dbo.dim_airlines AS t
    USING (
        SELECT c.dot_airline_id, c.carrier_code,
               COALESCE(n.airline_name, c.carrier_code) AS airline_name
        FROM carriers AS c
        LEFT JOIN names AS n ON n.carrier_code = c.carrier_code
    ) AS s
    ON t.dot_airline_id = s.dot_airline_id
    WHEN MATCHED THEN UPDATE SET
        carrier_code = s.carrier_code,
        airline_name = s.airline_name
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (dot_airline_id, carrier_code, airline_name)
        VALUES (s.dot_airline_id, s.carrier_code, s.airline_name);
END;
