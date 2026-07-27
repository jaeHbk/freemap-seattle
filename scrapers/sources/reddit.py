"""Reddit source: fetch free/BOGO deal posts from configured listing URLs.

Reads config.sources["reddit"]. Tested only against recorded payloads by
monkeypatching httpx.get; never hits the live network here.

User-Agent note: Reddit returns HTTP 403 to bare/non-browser clients, so this
source sends a browser-like UA (_BROWSER_USER_AGENT below) rather than
config.user_agent. config.user_agent is the polite, identifying UA shared with
Nominatim, whose policy REQUIRES an identifying contact UA; spoofing a browser
there would violate that policy, so the browser UA is scoped to this source.
"""
from __future__ import annotations

import re
from datetime import datetime

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal
from scrapers.deal_scope import is_target_deal

# Browser-like User-Agent sent ONLY on Reddit requests. Reddit 403s bare clients
# (the project's default identifying UA included), so we present a common desktop
# Chrome UA to get the public .json listing. Kept local to this source so the
# Nominatim-facing config.user_agent stays a polite, identifying contact string.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def _is_deal_candidate(title: str, selftext: str | None) -> bool:
    """True when the canonical scope module classifies the post Free/BOGO."""
    return is_target_deal(title, selftext)


# Lower-cased substrings that signal a physical supported-market location.
# Used to populate raw_location; classify() turns a non-None location into
# placement="physical". Conservative on purpose — false negatives just demote
# a deal to the list view, never drop it. These are distinctive multi-word
# neighborhood/venue names, so plain substring matching is safe.
_LOCATION_KEYWORDS = (
    "capitol hill",
    "ballard",
    "fremont",
    "downtown",
    "u district",
    "university district",
    "queen anne",
    "west seattle",
    "south lake union",
    "slu",
    "belltown",
    "seattle",
    "bellevue",
    "atlanta",
    "buckhead",
    "east atlanta village",
    "grant park",
    "inman park",
    "little five points",
    "midtown",
    "old fourth ward",
    "virginia-highland",
    "virginia highland",
    "west midtown",
)

# Address-shaped tokens that must match on word boundaries to avoid false
# positives: bare "ave"/"st." would otherwise fire on "save"/"have"/"gave"/
# "leave"/"waves", flipping an online deal to physical and wasting a
# rate-limited live geocode call on a non-address. \b anchors each abbreviation
# (and spelled-out form) to a real word, while "st\." keeps the trailing dot.
_LOCATION_PATTERN = re.compile(
    r"\b(?:ave|avenue|st\.|street|blvd|boulevard)\b",
    re.IGNORECASE,
)


def _extract_location(title: str, selftext: str | None) -> str | None:
    """Return a location string if the text mentions a known physical place."""
    haystack = f"{title} {selftext or ''}".lower()
    if any(kw in haystack for kw in _LOCATION_KEYWORDS) or _LOCATION_PATTERN.search(
        haystack
    ):
        # Hand the original (cased) text to the geocoder; it is the most
        # informative thing we have for a free-text Reddit post.
        return selftext or title
    return None


def _post_to_rawdeal(post: dict) -> RawDeal | None:
    """Map one Reddit post 'data' dict to a RawDeal. Returns None if unusable."""
    source_id = post.get("id")
    title = post.get("title")
    if not source_id or not title:
        return None

    permalink = post.get("permalink")
    url = post.get("url") or (
        f"https://www.reddit.com{permalink}" if permalink else ""
    )

    selftext = post.get("selftext") or None

    posted_at = None
    created = post.get("created_utc")
    if isinstance(created, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(created)
        except (OverflowError, OSError, ValueError):
            posted_at = None

    return RawDeal(
        source="reddit",
        source_id=source_id,
        title=title,
        url=url,
        description=selftext,
        raw_location=_extract_location(title, selftext),
        posted_at=posted_at,
        expires_at=None,
        raw=post,
    )


def fetch(config: Config) -> list[RawDeal]:
    """Fetch RawDeals from every configured Reddit listing URL.

    Never raises: a failed request or malformed listing for one URL is skipped
    so a single bad listing cannot abort the whole source.
    """
    settings = config.sources.get("reddit", {})
    listing_urls = settings.get("listing_urls", [])
    # Browser UA, not config.user_agent: Reddit 403s the identifying client UA.
    headers = {"User-Agent": _BROWSER_USER_AGENT}

    deals: list[RawDeal] = []
    for url in listing_urls:
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            payload = resp.json()
            # Guard every step: Reddit returns a JSON *array* for some endpoints
            # (e.g. comment-thread .json URLs), so payload/data may not be dicts.
            # Parsing must stay INSIDE the try so a non-dict shape skips this one
            # URL rather than aborting the loop (and any good URLs after it).
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            children = data.get("children", []) if isinstance(data, dict) else []
            if not isinstance(children, list):
                children = []
        except Exception:
            # One bad listing URL is skipped, not fatal.
            continue

        for child in children:
            post = (child or {}).get("data", {}) if isinstance(child, dict) else {}
            # Precision pre-filter: skip plain hot-feed posts with no deal signal
            # before mapping, so the classifier only ever sees deal candidates.
            if not _is_deal_candidate(post.get("title") or "", post.get("selftext")):
                continue
            raw_deal = _post_to_rawdeal(post)
            if raw_deal is not None:
                deals.append(raw_deal)

    return deals
