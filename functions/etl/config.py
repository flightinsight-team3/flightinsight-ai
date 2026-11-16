"""Project-wide ETL settings shared by every data source."""

# Scope: flights whose origin AND destination are both in this list.
# The 30 FAA large-hub airports by 2023 enplanements. DS03 builds dim_airports.is_top30
# from this same list, so the two always agree. Change it here, nowhere else.
TOP30_AIRPORTS: frozenset[str] = frozenset(
    {
        "ATL", "AUS", "BNA", "BOS", "BWI", "CLT", "DCA", "DEN", "DFW", "DTW",
        "EWR", "FLL", "IAD", "IAH", "JFK", "LAS", "LAX", "LGA", "MCO", "MDW",
        "MIA", "MSP", "ORD", "PHL", "PHX", "SAN", "SEA", "SFO", "SLC", "TPA",
    }
)  # fmt: skip

# Data Lake containers (see docs/etl-template.md for the path convention).
RAW_CONTAINER = "raw"
CLEAN_CONTAINER = "clean"
