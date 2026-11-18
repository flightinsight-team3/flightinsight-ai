"""Run one ETL step from the command line (the same code ADF calls through Azure Functions).

    cd functions
    python -m etl.run bts 202401 --local            # download from BTS, write to ../data/lake
    python -m etl.run bts 202401 --local --raw-file ../data/bts/bts_2024_01.zip     # no download
    python -m etl.run bts 202401                    # write to the Data Lake

The last form needs `az login` and the Storage Blob Data Contributor role on the Data Lake.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from etl import airports, bts, noaa
from etl.common import parse_month_key
from etl.storage import LakeSink, LocalSink

# source name → ingest_month(month_key, sink=..., raw=...). Add new sources here.
SOURCES = {
    "bts": bts.ingest_month,
    "airports": airports.ingest_month,
    "noaa": noaa.ingest_month,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run an ETL ingest step for one month.")
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("month_key", help="yyyymm, e.g. 202401")
    parser.add_argument("--local", action="store_true", help="write to data/lake instead of Azure")
    parser.add_argument("--raw-file", type=Path, help="use an already downloaded raw file")
    args = parser.parse_args(argv)

    month_key = parse_month_key(args.month_key)
    sink = LocalSink() if args.local else LakeSink()
    raw = args.raw_file.read_bytes() if args.raw_file else None
    result = SOURCES[args.source](month_key, sink=sink, raw=raw)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
