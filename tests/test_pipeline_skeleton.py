import inspect

from scrapers import pipeline


def test_all_stage_functions_exist():
    for name in ("normalize", "classify", "geocode_deal", "dedup",
                 "compute_status", "run_pipeline"):
        assert hasattr(pipeline, name), f"missing pipeline.{name}"
        assert callable(getattr(pipeline, name))


def test_run_pipeline_signature_is_canonical():
    sig = inspect.signature(pipeline.run_pipeline)
    assert list(sig.parameters) == ["raws", "geocoder", "conn", "now"]


def test_compute_status_signature_is_canonical():
    sig = inspect.signature(pipeline.compute_status)
    assert list(sig.parameters) == [
        "expires_at", "last_seen", "now", "stale_after_hours"
    ]
