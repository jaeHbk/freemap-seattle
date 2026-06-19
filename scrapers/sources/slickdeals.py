"""slickdeals source: parse a recorded deals-list page. Most deals are online-only
(no location); a deal-location span marks the occasional physical deal. Reads
config.user_agent and config.sources["slickdeals"]["listing_urls"]."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from scrapers.config import Config
from scrapers.contract import RawDeal


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("slickdeals", {})
    listing_urls: list[str] = settings.get("listing_urls", [])
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in listing_urls:
        # Per-URL isolation: a failed request, non-HTML body, or unexpected
        # structure for one URL is skipped, never fatal to the whole fetch.
        # Keep the fetch AND the parse inside this try.
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for art in soup.select("article.deal"):
                deal_id = art.get("data-deal-id") or ""
                title_el = art.select_one(".deal-title")
                summary_el = art.select_one(".deal-summary")
                url_el = art.select_one(".deal-url")
                location_el = art.select_one(".deal-location")

                title = title_el.get_text(strip=True) if title_el else ""
                # Skip malformed deals missing a stable id or title. Two id-less
                # deals would both get source_id "" and collide on the
                # UNIQUE(source, source_id) upsert, silently overwriting each
                # other. Mirror reddit's guard: a bad deal yields zero rows.
                if not deal_id or not title:
                    continue

                description = summary_el.get_text(strip=True) if summary_el else None
                deal_url = (url_el.get("href") if url_el else None) or url
                raw_location = (
                    location_el.get_text(strip=True) if location_el else None
                )

                deals.append(
                    RawDeal(
                        source="slickdeals",
                        source_id=deal_id,
                        title=title,
                        url=deal_url,
                        description=description,
                        raw_location=raw_location,
                        posted_at=None,
                        expires_at=None,
                        raw={"deal_id": deal_id, "listing_url": url},
                    )
                )
        except Exception:
            # One bad listing URL is skipped, not fatal.
            continue
    return deals
