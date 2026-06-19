"""Reddit source: fetch free/BOGO deal posts from configured listing URLs.

Reads config.user_agent and config.sources["reddit"]. Tested only against
recorded payloads by monkeypatching httpx.get; never hits the live network here.
"""
from __future__ import annotations

from datetime import datetime

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal

# Lower-cased substrings that signal a physical Seattle location in free text.
# Used to populate raw_location; classify() turns a non-None location into
# placement="physical". Conservative on purpose — false negatives just demote
# a deal to the list view, never drop it.
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
    "ave",
    "avenue",
    "street",
    "st.",
    "blvd",
)


def _extract_location(title: str, selftext: str | None) -> str | None:
    """Return a location string if the text mentions a known physical place."""
    haystack = f"{title} {selftext or ''}".lower()
    for kw in _LOCATION_KEYWORDS:
        if kw in haystack:
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
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in listing_urls:
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            # One bad listing URL is skipped, not fatal.
            continue

        children = (payload or {}).get("data", {}).get("children", [])
        for child in children:
            post = (child or {}).get("data", {})
            raw_deal = _post_to_rawdeal(post)
            if raw_deal is not None:
                deals.append(raw_deal)

    return deals
