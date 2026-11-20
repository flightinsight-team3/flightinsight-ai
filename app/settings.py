"""Settings for code that runs on a laptop: environment variables, filled from the repo's .env."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Copy KEY=VALUE lines from .env into os.environ. Variables already set win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)


def setting(name: str, default: str | None = None) -> str:
    """Read a setting; raise if it is missing and has no default."""
    value = os.getenv(name) or default
    if not value:
        raise RuntimeError(f"Missing setting: {name} (add it to .env, see .env.example)")
    return value
