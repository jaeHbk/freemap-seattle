from scrapers.config import Config, load_config


def test_load_config_reads_all_canonical_fields(tmp_path):
    cfg_text = """
[meta]
metro = "seattle"
db_path = "db/deals.db"
user_agent = "FreeMapSeattle/1.0 (contact: freemap@example.com)"
sources_enabled = ["reddit", "chains", "slickdeals", "local"]

[freshness]
stale_after_hours = 24

[geocoder]
min_interval_seconds = 1.0
max_live_calls = 200

[sources.reddit]
subreddits = ["Seattle", "SeattleWA"]
listing_urls = ["https://www.reddit.com/r/Seattle/search.json"]
"""
    p = tmp_path / "config.toml"
    p.write_text(cfg_text)

    cfg = load_config(str(p))

    assert isinstance(cfg, Config)
    assert cfg.metro == "seattle"
    assert cfg.db_path == "db/deals.db"
    assert cfg.stale_after_hours == 24
    assert cfg.user_agent == "FreeMapSeattle/1.0 (contact: freemap@example.com)"
    assert cfg.geocoder_min_interval_seconds == 1.0
    assert cfg.geocoder_max_live_calls == 200
    assert cfg.sources_enabled == ["reddit", "chains", "slickdeals", "local"]
    # per-source settings reachable as a plain dict (NEVER via .get on Config)
    assert cfg.sources["reddit"]["subreddits"] == ["Seattle", "SeattleWA"]


def test_geocoder_provider_defaults_to_census_not_nominatim(tmp_path):
    """A config that omits [geocoder].provider must default to the keyless 'census'
    geocoder — NOT 'nominatim', whose public endpoint 403s server traffic and would
    silently demote every physical deal to failed-geocode (the empty-map failure
    this whole effort exists to fix). load_config's fallback and the Config field
    default must agree."""
    p = tmp_path / "config.toml"
    p.write_text('[meta]\nmetro = "seattle"\n[geocoder]\nmin_interval_seconds = 1.0\n')

    cfg = load_config(str(p))
    assert cfg.geocoder_provider == "census"
    # The two defaults must not diverge.
    assert cfg.geocoder_provider == Config.__dataclass_fields__["geocoder_provider"].default


def test_load_config_applies_defaults_when_tables_absent(tmp_path):
    # Only [meta]; freshness/geocoder/sources omitted -> defaults fill in.
    p = tmp_path / "config.toml"
    p.write_text(
        '[meta]\n'
        'metro = "seattle"\n'
    )

    cfg = load_config(str(p))

    assert cfg.metro == "seattle"
    assert cfg.db_path == "db/deals.db"
    assert cfg.stale_after_hours == 24
    assert cfg.user_agent  # non-empty default User-Agent
    assert cfg.geocoder_min_interval_seconds == 1.0
    assert cfg.geocoder_max_live_calls == 200
    assert cfg.sources_enabled == ["reddit", "chains", "slickdeals", "local"]
    assert cfg.sources == {}


def test_committed_config_toml_loads_and_sources_reachable():
    # The real committed config at repo root must load and expose its source blocks.
    cfg = load_config("config.toml")
    assert cfg.metro == "seattle"
    # places_brand is the map-filling source and must be enabled; reddit/chains are
    # known-dead and intentionally dropped from the enabled set (their blocks remain
    # in the file for reference/reachability).
    assert "places_brand" in cfg.sources_enabled
    assert cfg.sources["places_brand"]["brands"]  # reachable, non-empty
    assert cfg.sources["reddit"]["subreddits"]  # block still reachable as a plain dict
