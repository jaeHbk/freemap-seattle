"""local source: parse a recorded local-deals RSS feed into physical RawDeals.
Each item carries a Seattle location, so the pipeline classifies these as physical.
Reads config.user_agent and config.sources["local"]["feed_urls"]."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

from scrapers.config import Config
from scrapers.contract import RawDeal


def _parse_pubdate(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None


def _text(item: ET.Element, tag: str) -> str | None:
    """Return the stripped text of <item>'s child <tag>, or None if absent/empty."""
    el = item.find(tag)
    if el is None or el.text is None:
        return None
    value = el.text.strip()
    return value or None


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("local", {})
    feed_urls: list[str] = settings.get("feed_urls", [])
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in feed_urls:
        # Per-URL isolation: a failed request or malformed feed for one URL is
        # skipped, never fatal to the whole fetch. Keep the fetch AND the parse
        # inside this try; ET.ParseError on a bad body falls through to skip.
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)

            for item in root.iter("item"):
                guid = _text(item, "guid") or ""
                title = _text(item, "title") or ""
                description = _text(item, "description")
                link = _text(item, "link") or url
                raw_location = _text(item, "location")
                posted_at = _parse_pubdate(_text(item, "pubDate"))

                deals.append(
                    RawDeal(
                        source="local",
                        source_id=guid,
                        title=title,
                        url=link,
                        description=description,
                        raw_location=raw_location,
                        posted_at=posted_at,
                        expires_at=None,
                        raw={"guid": guid, "feed_url": url},
                    )
                )
        except Exception:
            # A failed request or malformed feed (incl. ET.ParseError) never
            # aborts the run; skip this feed and continue with the others.
            continue
    return deals
