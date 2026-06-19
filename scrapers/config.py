import tomllib
from dataclasses import dataclass, field

# Default User-Agent used for ALL outbound requests (incl. Nominatim) when the
# config omits [meta].user_agent. Nominatim policy requires an identifying UA.
DEFAULT_USER_AGENT = "FreeMapSeattle/1.0 (contact: freemap@example.com)"


@dataclass
class Config:
    metro: str                                  # "seattle"
    db_path: str                                # "db/deals.db"
    stale_after_hours: int                      # 24
    user_agent: str                             # HTTP User-Agent for ALL outbound requests incl. Nominatim
    geocoder_min_interval_seconds: float        # 1.0
    geocoder_max_live_calls: int                # 200
    sources_enabled: list[str]                  # ["reddit", "chains", "slickdeals", "local"]
    sources: dict = field(default_factory=dict) # per-source settings


def load_config(path: str = "config.toml") -> Config:
    """Parse a TOML config file into the flat Config dataclass.

    Maps the [meta]/[freshness]/[geocoder]/[sources] tables onto the flat
    fields and fills in defaults for anything omitted. Reads in binary mode
    because tomllib.load requires a file opened with 'rb'.
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)

    meta = data.get("meta", {})
    freshness = data.get("freshness", {})
    geocoder = data.get("geocoder", {})
    sources = data.get("sources", {})

    return Config(
        metro=meta.get("metro", "seattle"),
        db_path=meta.get("db_path", "db/deals.db"),
        stale_after_hours=freshness.get("stale_after_hours", 24),
        user_agent=meta.get("user_agent", DEFAULT_USER_AGENT),
        geocoder_min_interval_seconds=geocoder.get("min_interval_seconds", 1.0),
        geocoder_max_live_calls=geocoder.get("max_live_calls", 200),
        sources_enabled=meta.get(
            "sources_enabled", ["reddit", "chains", "slickdeals", "local"]
        ),
        sources=sources,
    )
