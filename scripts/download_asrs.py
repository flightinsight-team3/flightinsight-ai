"""One-off: download NASA ASRS reports for a range of months as CSV.

ASRS Database Online (https://asrs.arc.nasa.gov/search/database.html) has no API, only an
ASP.NET query wizard. This script replays the clicks you would make in the browser:

    1. Start a new query
    2. Add the filter "Date of Incident" and set the first and last month
    3. Run the search
    4. Export the results as CSV

    python scripts/download_asrs.py --start 2024-01 --end 2024-03 --out data/asrs_2024Q1.csv

The output is the file scripts/embed_asrs.py expects. The wizard exports at most 10,000
reports per query, so split longer ranges into several downloads. If NASA changes the wizard
pages this script will stop working; the error says which step failed, and the same export
can still be made by hand in the browser.
"""

from __future__ import annotations

import argparse
import calendar
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.asrs.parse import parse_month  # noqa: E402

BASE = "https://dbol1-prod.arc.nasa.gov/ASRSPublicQueryWizard/"
EXPORT_LIMIT = 10_000
HIDDEN_INPUT = re.compile(r"<input[^>]*>", re.I)
ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
RESULT_COUNT = re.compile(r"returned\s+([\d,]+)\s+ACNs", re.I)
# Image buttons in the wizard are submitted as name.x / name.y click coordinates.
ADD_DATE_FILTER = {"2.x": "5", "2.y": "5"}
SAVE_DATES = {"SaveButton.x": "5", "SaveButton.y": "5"}
RUN_SEARCH = {"_ctl6.x": "5", "_ctl6.y": "5"}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    start, end = month_arg(args.start), month_arg(args.end)
    if start > end:
        sys.exit(f"--start {args.start} is after --end {args.end}")

    session = requests.Session()
    session.headers["User-Agent"] = "flightinsight-ai ASRS export (course project)"
    step("start a new query", lambda: get(session, "QueryWizard_StartNewQuery.aspx"))
    step(
        "add the Date of Incident filter",
        lambda: post_form(session, "QueryWizard_Filter.aspx", ADD_DATE_FILTER),
    )
    dates = {
        "DropDownList1": str(start // 100),
        "DropDownList2": calendar.month_name[start % 100],
        "DropDownList3": str(end // 100),
        "DropDownList4": calendar.month_name[end % 100],
        **SAVE_DATES,
    }
    page = "QueryWizard_DatePopup.aspx?statementId=2&statementType=Filter"
    step("set the months", lambda: post_form(session, page, dates))
    results = step(
        "run the search", lambda: post_form(session, "QueryWizard_Filter.aspx", RUN_SEARCH)
    )

    count = RESULT_COUNT.search(results)
    if count is None:
        sys.exit("Search ran but the result count was not found; the wizard may have changed.")
    total = int(count.group(1).replace(",", ""))
    print(f"ASRS returned {total:,} reports for {start}-{end}")
    if total > EXPORT_LIMIT:
        sys.exit(f"More than {EXPORT_LIMIT:,} reports: split the range into smaller downloads.")

    csv = step(
        "export CSV", lambda: get(session, "QueryWizard_ExportExcel.aspx?ExportType=CSV", raw=True)
    )
    if b"ACN" not in csv[:2000]:
        sys.exit("The export is not an ASRS CSV (no ACN column); the wizard may have changed.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(csv)
    print(f"Saved {len(csv):,} bytes to {args.out}")
    print(f"Next: python scripts/embed_asrs.py {args.out} --parse-only")
    return 0


def step(name: str, call):
    try:
        return call()
    except requests.RequestException as e:
        sys.exit(f"ASRS step '{name}' failed: {e}")


def get(session: requests.Session, page: str, raw: bool = False):
    response = session.get(BASE + page, timeout=300)
    response.raise_for_status()
    return response.content if raw else response.text


def post_form(session: requests.Session, page: str, fields: dict) -> str:
    """Load an ASP.NET page and post it back with its hidden state plus our fields."""
    response = session.post(
        BASE + page, data={**hidden_fields(get(session, page)), **fields}, timeout=120
    )
    response.raise_for_status()
    return response.text


def hidden_fields(html: str) -> dict[str, str]:
    """__VIEWSTATE and the other hidden inputs ASP.NET needs on every post-back."""
    fields = {}
    for tag in HIDDEN_INPUT.findall(html):
        attrs = {k.lower(): v for k, v in ATTRIBUTE.findall(tag)}
        if attrs.get("type", "").lower() == "hidden" and "name" in attrs:
            fields[attrs["name"]] = attrs.get("value", "")
    return fields


def month_arg(value: str) -> int:
    month = parse_month(value)
    if month is None:
        sys.exit(f"Not a month: {value!r} (use 2024-01)")
    return month


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--start", required=True, help="first month, e.g. 2024-01")
    parser.add_argument("--end", required=True, help="last month, e.g. 2024-03")
    parser.add_argument(
        "--out", type=Path, required=True, help="CSV path, e.g. data/asrs_2024Q1.csv"
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
