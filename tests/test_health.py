"""Tests for scrapers.health — the post-scrape source-health baseline check.

The core decision is the PURE function evaluate_health(latest_by_source, expected,
optional) -> {"ok": bool, "problems": [...]}, so these tests need no DB. The
baseline mirrors config.toml [health]: places_brand is required and
rate-limit-prone Reddit is optional.
"""
from datetime import datetime, timedelta

from scrapers.health import (
    evaluate_health,
    format_report,
    read_fresh_pin_counts,
)
from tests.conftest import FIXED_NOW

EXPECTED = ["places_brand"]
OPTIONAL = ["reddit"]


def _run(found, errors=None):
    """Shape one latest-scrape_runs row the way read_latest_runs returns it."""
    return {"deals_found": found, "errors": errors}


def test_all_expected_healthy_is_ok():
    latest = {
        "places_brand": _run(9),
        # Optional Reddit may be rate-limited without failing the run.
        "reddit": _run(0),
    }
    result = evaluate_health(latest, EXPECTED, OPTIONAL)
    assert result["ok"] is True
    assert result["problems"] == []


def test_expected_source_errored_fails():
    latest = {
        "places_brand": _run(0, errors="Places API 500"),
    }
    result = evaluate_health(latest, EXPECTED, OPTIONAL)
    assert result["ok"] is False
    assert any(p["source"] == "places_brand" for p in result["problems"])


def test_expected_source_zero_found_fails():
    latest = {
        "places_brand": _run(0),  # no error, but found nothing — still a failure
    }
    result = evaluate_health(latest, EXPECTED, OPTIONAL)
    assert result["ok"] is False
    problems = {p["source"] for p in result["problems"]}
    assert problems == {"places_brand"}


def test_expected_source_without_required_map_pins_fails():
    result = evaluate_health(
        {"places_brand": _run(15)},
        EXPECTED,
        OPTIONAL,
        pin_counts={"places_brand": 0},
        minimum_pins={"places_brand": 1},
    )

    assert result["ok"] is False
    assert result["problems"][0]["reason"] == (
        "found 0 fresh map pins (minimum: 1)"
    )


def test_expected_source_with_required_map_pins_passes():
    result = evaluate_health(
        {"places_brand": _run(15)},
        EXPECTED,
        OPTIONAL,
        pin_counts={"places_brand": 14},
        minimum_pins={"places_brand": 1},
    )

    assert result["ok"] is True


def test_expected_source_below_deal_coverage_floor_fails():
    result = evaluate_health(
        {"places_brand": _run(39)},
        EXPECTED,
        OPTIONAL,
        pin_counts={"places_brand": 38},
        minimum_pins={"places_brand": 38},
        minimum_deals={"places_brand": 40},
    )

    assert result["ok"] is False
    assert result["problems"][0]["reason"] == (
        "found 39 deals (minimum: 40)"
    )


def test_expected_source_at_coverage_floors_passes():
    result = evaluate_health(
        {"places_brand": _run(40)},
        EXPECTED,
        OPTIONAL,
        pin_counts={"places_brand": 38},
        minimum_pins={"places_brand": 38},
        minimum_deals={"places_brand": 40},
    )

    assert result["ok"] is True


def test_health_report_includes_operational_telemetry():
    latest = {
        "places_brand": {
            "deals_found": 40,
            "deals_upserted": 40,
            "map_pins": 38,
            "geocode_failures": 2,
            "duration_ms": 1250,
            "errors": None,
        }
    }
    result = evaluate_health(
        latest,
        EXPECTED,
        OPTIONAL,
        pin_counts={"places_brand": 38},
        minimum_pins={"places_brand": 38},
        minimum_deals={"places_brand": 40},
    )

    report = format_report(
        result,
        latest,
        EXPECTED,
        OPTIONAL,
        pin_counts={"places_brand": 38},
        minimum_pins={"places_brand": 38},
    )

    assert "found=40 upserted=40 pins=38" in report
    assert "geocode_failed=2 duration_ms=1250" in report
    assert report.endswith("HEALTHY")


def test_fresh_pin_query_excludes_old_failed_online_and_expired_rows(seeded_db):
    conn, _ = seeded_db

    counts = read_fresh_pin_counts(
        conn, FIXED_NOW - timedelta(hours=2), FIXED_NOW
    )

    assert counts == {"reddit": 1, "slickdeals": 2}


def test_optional_source_failure_is_still_ok():
    """A rate-limited Reddit run must not make the health gate fail."""
    latest = {
        "places_brand": _run(9),
        "reddit": _run(0, errors="403 Forbidden"),
    }
    result = evaluate_health(latest, EXPECTED, OPTIONAL)
    assert result["ok"] is True
    assert result["problems"] == []


def test_missing_expected_source_fails():
    """An expected source with no scrape_runs row at all (never ran / row lost) is a
    failure — silence is not health."""
    latest = {}  # places_brand entirely absent
    result = evaluate_health(latest, EXPECTED, OPTIONAL)
    assert result["ok"] is False
    problems = {p["source"] for p in result["problems"]}
    assert "places_brand" in problems


# --- recency / stale-row false-green guard ----------------------------------
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
    }
    result = evaluate_health(latest, EXPECTED, OPTIONAL, now=_NOW, max_age_hours=48)
    assert result["ok"] is False
    stale = [p for p in result["problems"] if p["source"] == "places_brand"]
    assert stale and "fresh" in stale[0]["reason"]


def test_fresh_rows_pass_with_recency_enabled():
    latest = {s: _run_at(9, hours_ago=1) for s in EXPECTED}
    result = evaluate_health(latest, EXPECTED, OPTIONAL, now=_NOW, max_age_hours=48)
    assert result["ok"] is True


def test_recency_disabled_preserves_old_behavior():
    """max_age_hours=None (or now=None) keeps the original latest-row semantics."""
    latest = {s: _run_at(9, hours_ago=999) for s in EXPECTED}
    result = evaluate_health(latest, EXPECTED, OPTIONAL)  # no now/window
    assert result["ok"] is True
