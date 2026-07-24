from datetime import datetime, timedelta

from scrapers import pipeline
from scrapers.config import load_config
from scrapers.contract import Deal, RawDeal
from scrapers.db import fetch_all_deals
from scrapers.geocode import FakeGeocoder
from scrapers.pipeline import run_pipeline
from scrapers.publication import evaluate_candidate
from scrapers.quality import build_quality_report
from scrapers.sources import places_brand

NOW = datetime(2026, 7, 23, 12, 0, 0)


def _deal(**overrides) -> Deal:
    values = {
        "source": "reddit",
        "source_id": "one",
        "title": "Free coffee",
        "url": "https://example.com/free-coffee",
        "description": None,
        "deal_type": "free",
        "category": "food",
        "placement": "online",
        "lat": None,
        "lng": None,
        "raw_location": None,
        "geocode_status": "n/a",
        "posted_at": None,
        "expires_at": None,
    }
    values.update(overrides)
    return Deal(**values)


def test_publication_policy_requires_official_evidence_or_corroboration():
    community = evaluate_candidate(
        _deal(),
        tier="community",
        now=NOW,
        independent_source_count=1,
    )
    corroborated = evaluate_candidate(
        _deal(),
        tier="community",
        now=NOW,
        independent_source_count=2,
    )
    official = evaluate_candidate(
        _deal(source="places_brand", verified_at=NOW),
        tier="official",
        now=NOW,
        independent_source_count=1,
    )
    ordinary_discount = evaluate_candidate(
        _deal(deal_type="other", title="20% off coffee"),
        tier="aggregator",
        now=NOW,
        independent_source_count=1,
    )

    assert (community.decision, community.reason) == (
        "pending",
        "independent_corroboration_required",
    )
    assert corroborated.decision == "accepted"
    assert corroborated.verification_status == "corroborated"
    assert official.decision == "accepted"
    assert official.verification_status == "official"
    assert (ordinary_discount.decision, ordinary_discount.reason) == (
        "rejected",
        "out_of_scope",
    )


def test_official_verification_uses_full_calendar_day_window():
    verified = datetime(2026, 6, 23)
    day_30 = evaluate_candidate(
        _deal(source="places_brand", verified_at=verified),
        tier="official",
        now=datetime(2026, 7, 23, 23, 59),
        independent_source_count=1,
    )
    day_31 = evaluate_candidate(
        _deal(source="places_brand", verified_at=verified),
        tier="official",
        now=datetime(2026, 7, 24),
        independent_source_count=1,
    )

    assert day_30.decision == "accepted"
    assert (day_31.decision, day_31.reason) == (
        "pending",
        "official_verification_stale",
    )


def test_official_candidate_persists_evidence_and_publication_provenance(conn):
    raw = RawDeal(
        source="places_brand",
        source_id="museum::seattle",
        title="Free museum admission every day",
        url="https://museum.example/visit",
        description="Official admission terms",
        eligibility="All visitors",
        redemption="Visit during public hours",
        verified_at=NOW,
        raw_location="704 Terry Ave, Seattle, WA 98104",
    )
    geocoder = FakeGeocoder(
        {"704 Terry Ave, Seattle, WA 98104": (47.6073, -122.3241)}
    )

    assert run_pipeline([raw], geocoder, conn, NOW) == 1
    assert run_pipeline([raw], geocoder, conn, NOW + timedelta(hours=1)) == 1

    candidate = conn.execute("SELECT * FROM deal_candidates").fetchone()
    evidence = conn.execute("SELECT * FROM deal_evidence").fetchall()
    published = fetch_all_deals(conn)[0]
    assert candidate["decision"] == "accepted"
    assert candidate["decision_reason"] == "current_official_evidence"
    assert len(evidence) == 1
    assert evidence[0]["evidence_type"] == "official_terms"
    assert evidence[0]["excerpt"].startswith("Free museum admission")
    assert published["candidate_id"] == candidate["id"]
    assert published["verification_status"] == "official"
    assert published["evidence_count"] == 1
    assert published["quality_score"] == 100


def test_matching_independent_sources_publish_only_corroborated_claim(conn):
    title = "Free online Seattle workshop"
    reddit = RawDeal(
        source="reddit",
        source_id="r1",
        title=title,
        url="https://reddit.example/r1",
    )
    editorial = RawDeal(
        source="local",
        source_id="l1",
        title=title,
        url="https://local.example/l1",
    )

    assert run_pipeline([reddit], FakeGeocoder({}), conn, NOW) == 0
    assert run_pipeline([editorial], FakeGeocoder({}), conn, NOW) == 1

    decisions = {
        row["source"]: row["decision"]
        for row in conn.execute("SELECT source, decision FROM deal_candidates")
    }
    published = fetch_all_deals(conn)
    assert decisions == {"reddit": "pending", "local": "accepted"}
    assert len(published) == 1
    assert published[0]["verification_status"] == "corroborated"
    assert published[0]["evidence_count"] == 2


def test_candidate_is_unpublished_when_current_evidence_no_longer_passes(conn):
    valid = RawDeal(
        source="places_brand",
        source_id="offer::store",
        title="Free coffee",
        url="https://example.com/terms",
        verified_at=NOW,
    )
    needs_review = RawDeal(
        source="places_brand",
        source_id="offer::store",
        title="Free coffee",
        url="https://example.com/terms",
        verified_at=None,
    )

    assert run_pipeline([valid], FakeGeocoder({}), conn, NOW) == 1
    assert run_pipeline(
        [needs_review],
        FakeGeocoder({}),
        conn,
        NOW + timedelta(hours=1),
    ) == 0

    assert fetch_all_deals(conn) == []
    candidate = conn.execute("SELECT * FROM deal_candidates").fetchone()
    assert candidate["decision"] == "pending"
    assert candidate["decision_reason"] == "official_verification_required"


def test_evidence_processing_failure_unpublishes_previous_acceptance(
    conn,
    monkeypatch,
):
    raw = RawDeal(
        source="places_brand",
        source_id="offer::store",
        title="Free coffee",
        url="https://example.com/terms",
        verified_at=NOW,
    )
    assert run_pipeline([raw], FakeGeocoder({}), conn, NOW) == 1

    def fail_evidence(*args, **kwargs):
        raise RuntimeError("evidence store unavailable")

    monkeypatch.setattr(pipeline, "upsert_evidence", fail_evidence)
    assert run_pipeline(
        [raw],
        FakeGeocoder({}),
        conn,
        NOW + timedelta(hours=1),
    ) == 0

    assert fetch_all_deals(conn) == []
    candidate = conn.execute("SELECT * FROM deal_candidates").fetchone()
    assert candidate["decision"] == "pending"
    assert candidate["decision_reason"] == "evidence_processing_failed"


def test_quality_and_breadth_improve_against_committed_baseline(conn):
    """Deterministic proof: broader discovery cannot leak noise onto the map."""
    config = load_config("config.toml")
    official_raws = places_brand.fetch(config, now=NOW)
    locations = {
        raw.raw_location: (47.61, -122.33)
        for raw in official_raws
        if raw.raw_location
    }
    assert run_pipeline(
        official_raws,
        FakeGeocoder(locations),
        conn,
        NOW,
    ) == 44

    broad_discovery = [
        RawDeal(
            source="reddit",
            source_id="community-free",
            title="Free community coffee",
            url="https://reddit.example/free",
        ),
        RawDeal(
            source="chains",
            source_id="official-discount",
            title="20% off happy hour",
            url="https://restaurant.example/happy-hour",
        ),
        RawDeal(
            source="slickdeals",
            source_id="aggregator-free",
            title="Free online sample",
            url="https://deals.example/free",
        ),
        RawDeal(
            source="local",
            source_id="editorial-news",
            title="Neighborhood business news",
            url="https://local.example/news",
        ),
    ]
    for raw in broad_discovery:
        run_pipeline([raw], FakeGeocoder({}), conn, NOW)

    report = build_quality_report(conn)
    legacy = {
        "candidate_source_count": 2,
        "published_deal_count": 43,
        "published_category_count": 2,
        "published_map_pins": 43,
    }

    assert report["quality_gate_passed"] is True
    assert report["published_policy_violations"] == 0
    assert report["candidate_source_count"] == 5
    assert report["candidate_source_tier_count"] == 4
    assert report["candidate_decisions"] == {
        "accepted": 44,
        "pending": 2,
        "rejected": 2,
    }
    assert report["published_deal_count"] == 44
    assert report["published_category_count"] == 3
    assert report["published_map_pins"] == 44
    assert report["minimum_published_quality_score"] == 100

    assert report["candidate_source_count"] > legacy["candidate_source_count"]
    assert report["published_deal_count"] > legacy["published_deal_count"]
    assert report["published_category_count"] > legacy["published_category_count"]
    assert report["published_map_pins"] > legacy["published_map_pins"]
