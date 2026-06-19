import subprocess
import sys
from pathlib import Path

import httpx

import scrapers.run as run_module
from scrapers.geocode import FakeGeocoder

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


def test_missing_config_clean_error(capsys):
    """A missing --config exits 1 with a clean stderr message, no traceback."""
    exit_code = run_module.main(["--config", "/nonexistent-freemap.toml"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "config not found: /nonexistent-freemap.toml" in captured.err


_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# URL -> fixture filename. The temp config.toml below sets these exact URLs so
# each source's httpx.get(url) is served the matching recorded payload.
_URL_TO_FIXTURE = {
    "https://test.local/reddit": "reddit_sample.json",
    "https://test.local/chains": "chains_offers.html",
    "https://test.local/slickdeals": "slickdeals_list.html",
    "https://test.local/local": "local_feed.xml",
}


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body
        self.status_code = 200

    @property
    def text(self) -> str:
        return self._body.decode("utf-8")

    @property
    def content(self) -> bytes:
        return self._body

    def json(self):
        import json

        return json.loads(self._body.decode("utf-8"))

    def raise_for_status(self):
        return None


def _fake_httpx_get(url, *args, **kwargs):
    for prefix, filename in _URL_TO_FIXTURE.items():
        if url.startswith(prefix):
            body = (_FIXTURES_DIR / filename).read_bytes()
            return _FakeResponse(body)
    raise AssertionError(f"Unexpected live URL in offline test: {url}")


_CONFIG_TOML = """
[meta]
metro = "seattle"
db_path = "PLACEHOLDER_DB"
user_agent = "FreeMapTest/1.0 (offline-test)"
sources_enabled = ["reddit", "chains", "slickdeals", "local"]

[freshness]
stale_after_hours = 24

[geocoder]
min_interval_seconds = 0.0
max_live_calls = 0

[sources.reddit]
subreddits = ["seattle"]
listing_urls = ["https://test.local/reddit"]

[sources.chains]
offers_urls = ["https://test.local/chains"]

[sources.chains.branches]
"Capitol Hill" = "Capitol Hill, Seattle"

[sources.slickdeals]
listing_urls = ["https://test.local/slickdeals"]

[sources.local]
feed_urls = ["https://test.local/local"]
"""


def test_full_offline_run_populates_db_and_scrape_runs(tmp_path, monkeypatch):
    """main() over the four recorded fixtures fills `deals` and writes one
    `scrape_runs` row per enabled source, with exit code 0 — no network."""
    db_file = tmp_path / "deals.db"
    config_file = tmp_path / "config.toml"
    config_file.write_text(_CONFIG_TOML.replace("PLACEHOLDER_DB", str(db_file)))

    # No live network: every source's httpx.get is served a recorded fixture.
    monkeypatch.setattr(httpx, "get", _fake_httpx_get)

    # No live Nominatim: replace the Geocoder main() constructs with a
    # FakeGeocoder. Any Seattle-ish raw_location resolves; misses -> None.
    class _PatchedGeocoder:
        def __init__(self, *args, **kwargs):
            self._fake = FakeGeocoder(
                {
                    "Capitol Hill": (47.6253, -122.3222),
                    "Capitol Hill, Seattle": (47.6253, -122.3222),
                    "Downtown Seattle": (47.6062, -122.3321),
                    "Ballard": (47.6685, -122.3838),
                }
            )

        def geocode(self, raw_location):
            return self._fake.geocode(raw_location)

    monkeypatch.setattr(run_module, "Geocoder", _PatchedGeocoder)

    exit_code = run_module.main(["--config", str(config_file), "--db", str(db_file)])

    # At least one source ran cleanly -> exit 0.
    assert exit_code == 0

    # DB exists and has rows.
    assert db_file.exists()
    from scrapers.db import connect

    conn = connect(str(db_file))
    deal_count = conn.execute("SELECT COUNT(*) AS c FROM deals").fetchone()["c"]
    assert deal_count > 0, "expected the offline fixtures to produce >=1 deal"

    # Exactly one scrape_runs row per enabled source for this run.
    rows = conn.execute(
        "SELECT source FROM scrape_runs ORDER BY source"
    ).fetchall()
    sources_recorded = sorted(r["source"] for r in rows)
    assert sources_recorded == ["chains", "local", "reddit", "slickdeals"]
    assert len(rows) == 4
    conn.close()
