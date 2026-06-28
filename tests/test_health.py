"""Tests for scrapers.health — the post-scrape source-health baseline check.

The core decision is the PURE function evaluate_health(latest_by_source, expected,
known_dead) -> {"ok": bool, "problems": [...]}, so these tests need no DB. The
baseline mirrors config.toml [health]: expected = the three healthy sources,
known_dead = reddit/chains which record 0/None forever and must NEVER alert.
"""
from scrapers.health import evaluate_health

EXPECTED = ["places_brand", "slickdeals", "local"]
KNOWN_DEAD = ["reddit", "chains"]


def _run(found, errors=None):
    """Shape one latest-scrape_runs row the way read_latest_runs returns it."""
    return {"deals_found": found, "errors": errors}


def test_all_expected_healthy_is_ok():
    latest = {
        "places_brand": _run(9),
        "slickdeals": _run(50),
        "local": _run(30),
        # known-dead present with 0 found / no error — the normal steady state.
        "reddit": _run(0),
        "chains": _run(0),
    }
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD)
    assert result["ok"] is True
    assert result["problems"] == []


def test_expected_source_errored_fails():
    latest = {
        "places_brand": _run(0, errors="Places API 500"),
        "slickdeals": _run(50),
        "local": _run(30),
    }
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD)
    assert result["ok"] is False
    assert any(p["source"] == "places_brand" for p in result["problems"])


def test_expected_source_zero_found_fails():
    latest = {
        "places_brand": _run(9),
        "slickdeals": _run(0),  # no error, but found nothing — still a failure
        "local": _run(30),
    }
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD)
    assert result["ok"] is False
    problems = {p["source"] for p in result["problems"]}
    assert problems == {"slickdeals"}


def test_known_dead_source_dead_is_still_ok():
    """reddit/chains return 0 or error every run — that is the EXPECTED state and
    must NOT make the check fail or even appear as a problem."""
    latest = {
        "places_brand": _run(9),
        "slickdeals": _run(50),
        "local": _run(30),
        "reddit": _run(0, errors="403 Forbidden"),
        "chains": _run(0),
    }
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD)
    assert result["ok"] is True
    assert result["problems"] == []


def test_missing_expected_source_fails():
    """An expected source with no scrape_runs row at all (never ran / row lost) is a
    failure — silence is not health."""
    latest = {
        "slickdeals": _run(50),
        "local": _run(30),
        # places_brand entirely absent
    }
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD)
    assert result["ok"] is False
    problems = {p["source"] for p in result["problems"]}
    assert "places_brand" in problems


# --- recency / stale-row false-green guard ----------------------------------
from datetime import datetime, timedelta  # noqa: E402

_NOW = datetime(2026, 6, 27, 12, 0, 0)


def _run_at(found, hours_ago, errors=None):
    return {
        "deals_found": found,
        "errors": errors,
        "finished_at": (_NOW - timedelta(hours=hours_ago)).isoformat(),
    }


def test_stale_healthy_row_fails_when_recency_enabled():
    """A source that did NOT run this cycle but has a healthy row from a prior
    cycle must FAIL when a recency window is set — the dangerous false-green."""
    latest = {
        "places_brand": _run_at(9, hours_ago=72),   # 3 days old -> stale
        "slickdeals": _run_at(50, hours_ago=1),
        "local": _run_at(30, hours_ago=1),
    }
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD, now=_NOW, max_age_hours=48)
    assert result["ok"] is False
    stale = [p for p in result["problems"] if p["source"] == "places_brand"]
    assert stale and "fresh" in stale[0]["reason"]


def test_fresh_rows_pass_with_recency_enabled():
    latest = {s: _run_at(9, hours_ago=1) for s in EXPECTED}
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD, now=_NOW, max_age_hours=48)
    assert result["ok"] is True


def test_recency_disabled_preserves_old_behavior():
    """max_age_hours=None (or now=None) keeps the original latest-row semantics."""
    latest = {s: _run_at(9, hours_ago=999) for s in EXPECTED}
    result = evaluate_health(latest, EXPECTED, KNOWN_DEAD)  # no now/window
    assert result["ok"] is True
