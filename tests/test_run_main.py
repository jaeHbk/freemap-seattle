import subprocess
import sys
from pathlib import Path

# Repo root = parent of the tests/ directory. Used as the subprocess cwd so
# `python -m scrapers.run` resolves the package regardless of where pytest runs.
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_help_exits_zero():
    """`python -m scrapers.run --help` must exit 0 and mention --db/--config."""
    result = subprocess.run(
        [sys.executable, "-m", "scrapers.run", "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--db" in result.stdout
    assert "--config" in result.stdout
