"""Every sample document must match its schema, so schema and examples never drift apart."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

COSMOS = Path(__file__).resolve().parents[1] / "cosmos"
PAIRS = [
    ("route_summary.schema.json", "route_summary.sample.json"),
    ("asrs_report.schema.json", "asrs_report.sample.json"),
]


@pytest.mark.parametrize("schema_file,sample_file", PAIRS)
def test_sample_matches_schema(schema_file, sample_file):
    schema = json.loads((COSMOS / "schemas" / schema_file).read_text())
    sample = json.loads((COSMOS / "samples" / sample_file).read_text())
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(sample), key=str)
    assert not errors, "\n".join(e.message for e in errors)
