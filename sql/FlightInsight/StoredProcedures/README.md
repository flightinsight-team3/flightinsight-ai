T-SQL stored procedures (`usp_*`) that move data from staging into the star schema,
called by ADF Stored Procedure activities. One procedure per file, e.g. `usp_load_fact_flights.sql`.
Each procedure should delete-and-reload one month so re-running it never creates duplicates.
