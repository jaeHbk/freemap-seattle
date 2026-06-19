# tests/test_pipeline_integration.py
from scrapers.contract import RawDeal
from scrapers.db import fetch_all_deals
from scrapers.geocode import FakeGeocoder
from scrapers.pipeline import run_pipeline


def _raw(source_id, title, raw_location=None):
    return RawDeal(
        source="reddit",
        source_id=source_id,
        title=title,
        url=f"http://x/{source_id}",
        raw_location=raw_location,
    )


def test_run_pipeline_end_to_end_inserts_rows(conn, now):
    geocoder = FakeGeocoder({"Capitol Hill": (47.6, -122.3)})
    raws = [
        _raw("1", "Free coffee", "Capitol Hill"),   # physical, geocodes ok
        _raw("2", "Free ebook download"),            # online
        _raw("3", "Buy one get one free pizza", "Unknown Place"),  # geocode fails
    ]
    n = run_pipeline(raws, geocoder, conn, now)
    assert n == 3
    rows = {r["source_id"]: r for r in fetch_all_deals(conn)}
    assert len(rows) == 3
    assert rows["1"]["geocode_status"] == "ok"
    assert rows["1"]["placement"] == "physical"
    assert rows["2"]["placement"] == "online"
    assert rows["2"]["geocode_status"] == "n/a"
    assert rows["3"]["deal_type"] == "bogo"
    assert rows["3"]["geocode_status"] == "failed"
    # every row got a dedup_key
    assert all(rows[k]["dedup_key"] for k in rows)


def test_run_pipeline_one_malformed_raw_does_not_abort_batch(conn, now):
    geocoder = FakeGeocoder({})

    class Exploding(RawDeal):
        @property
        def title(self):  # blows up inside normalize when accessed
            raise ValueError("boom")

        @title.setter
        def title(self, v):
            pass

    bad = Exploding(source="reddit", source_id="bad", title="x", url="http://x")
    good = _raw("ok", "Free coffee")
    n = run_pipeline([bad, good], geocoder, conn, now)
    rows = [r["source_id"] for r in fetch_all_deals(conn)]
    assert rows == ["ok"]   # bad row skipped, batch survived
    assert n == 1


def test_run_pipeline_returns_zero_for_empty_input(conn, now):
    assert run_pipeline([], FakeGeocoder({}), conn, now) == 0
