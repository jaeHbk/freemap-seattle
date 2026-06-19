"""chains source: parse a chain's offers page and expand each offer to every
configured Seattle branch location (so a single chain-wide BOGO becomes one
physical RawDeal per branch). Reads config.user_agent and config.sources["chains"]."""

from __future__ import annotations

from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from scrapers.config import Config
from scrapers.contract import RawDeal


def _parse_expires(time_el) -> datetime | None:
    if time_el is None:
        return None
    raw = time_el.get("datetime") or time_el.get_text(strip=True)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("chains", {})
    offers_urls: list[str] = settings.get("offers_urls", [])
    branches: dict = settings.get("branches", {})
    headers = {"User-Agent": config.user_agent}

    deals: list[RawDeal] = []
    for url in offers_urls:
        # Per-URL isolation: a failed request, non-HTML body, or unexpected
        # structure for one URL is skipped, never fatal to the whole fetch.
        # Keep the fetch AND the parse inside this try.
        try:
            resp = httpx.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for offer in soup.select("li.offer"):
                offer_id = offer.get("data-offer-id") or ""
                title_el = offer.select_one(".offer-title")
                desc_el = offer.select_one(".offer-desc")
                link_el = offer.select_one(".offer-link")
                expires_el = offer.select_one(".offer-expires")

                title = title_el.get_text(strip=True) if title_el else ""
                description = desc_el.get_text(strip=True) if desc_el else None
                offer_url = (link_el.get("href") if link_el else None) or url
                expires_at = _parse_expires(expires_el)

                for branch_name, branch_address in branches.items():
                    # Composite id keeps each branch a distinct upsert row.
                    source_id = f"{offer_id}::{branch_name}"
                    deals.append(
                        RawDeal(
                            source="chains",
                            source_id=source_id,
                            title=title,
                            url=offer_url,
                            description=description,
                            raw_location=branch_address,
                            posted_at=None,
                            expires_at=expires_at,
                            raw={
                                "offer_id": offer_id,
                                "branch": branch_name,
                                "offers_url": url,
                            },
                        )
                    )
        except Exception:
            # One bad offers URL is skipped, not fatal.
            continue
    return deals
