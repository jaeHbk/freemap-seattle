import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

# Repo root = parent of the tests/ directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

# Fixed clock for deterministic freshness assertions across the whole suite.
NOW = datetime(2026, 6, 18, 12, 0, 0)


@pytest.fixture
def now():
    """A fixed 'now' so freshness tests never depend on the wall clock."""
    return NOW


@pytest.fixture
def conn():
    """In-memory SQLite connection with the committed schema applied.

    row_factory = sqlite3.Row so rows are accessible by column name, matching
    what scrapers.db.connect() produces.
    """
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_PATH.read_text())
    yield connection
    connection.close()
