# tests/

pytest tests run by CI on every PR. `pytest -q` from the repo root.
Put tests for `functions/etl/*` here (e.g. `test_bts_cleaning.py`). Don't call real Azure services in tests.
