# tests/test_classify.py
from scrapers.contract import RawDeal
from scrapers.pipeline import classify


def _raw(title="t", description=None, raw_location=None):
    return RawDeal(
        source="reddit",
        source_id="abc",
        title=title,
        url="http://x",
        description=description,
        raw_location=raw_location,
    )


# ---- deal_type ----
def test_deal_type_free():
    assert classify(_raw(title="Free coffee today")).deal_type == "free"


def test_deal_type_free_requires_a_complete_word():
    assert classify(_raw(title="Deep Freeze cooler")).deal_type == "other"


def test_deal_type_giveaway_is_free():
    assert classify(_raw(title="Neighborhood book giveaway")).deal_type == "free"


def test_deal_type_bogo_overrides_free_via_buy_one():
    assert classify(_raw(title="Buy one get one free pizza")).deal_type == "bogo"


def test_deal_type_buy_one_without_get_one_is_not_bogo():
    assert classify(_raw(title="Buy one pizza for ten dollars")).deal_type == "other"


def test_deal_type_bogo_via_b1g1():
    assert classify(_raw(title="B1G1 burrito deal")).deal_type == "bogo"


def test_deal_type_other_via_percent_off():
    assert classify(_raw(title="50% off shoes")).deal_type == "other"


def test_deal_type_other_default():
    assert classify(_raw(title="Cool concert announcement")).deal_type == "other"


# ---- placement ----
def test_placement_physical_when_location_present():
    assert classify(_raw(raw_location="Capitol Hill")).placement == "physical"


def test_placement_online_when_no_location():
    d = classify(_raw(raw_location=None))
    assert d.placement == "online"
    assert d.geocode_status == "n/a"
    assert d.lat is None and d.lng is None


def test_physical_starts_pending_geocode():
    d = classify(_raw(raw_location="1429 12th Ave"))
    assert d.geocode_status == "pending"
    assert d.lat is None and d.lng is None


# ---- category ----
def test_category_food():
    assert classify(_raw(title="Free pizza and coffee")).category == "food"


def test_category_event():
    assert classify(_raw(title="Free concert festival")).category == "event"


def test_category_retail():
    assert classify(_raw(title="Free shoes at the store")).category == "retail"


def test_category_other():
    assert classify(_raw(title="Free advice")).category == "other"


# ---- field passthrough ----
def test_passes_through_identity_fields():
    d = classify(_raw(title="Free coffee", description="desc", raw_location="X"))
    assert d.source == "reddit"
    assert d.source_id == "abc"
    assert d.url == "http://x"
    assert d.description == "desc"
    assert d.raw_location == "X"
