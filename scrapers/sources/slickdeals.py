"""slickdeals source: parse a public deals-listing page into RawDeals.

Despite the module name, the wired source is DealNews (https://www.dealnews.com/),
a server-rendered deals front page. Each offer is exposed on a <button> action
element carrying data-content-id (stable id), data-content-type="OFFER", an
absolute data-offer-url, and the human-readable title URL-encoded as the `t=`
query param inside the data-share-*-url attributes (the title is NOT visible
text on that element). All DealNews offers are online (no location), so they
surface as online deals in the list view. Reads config.user_agent and
config.sources["slickdeals"]["listing_urls"]."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from scrapers.config import Config
from scrapers.contract import RawDeal

# Share-URL attributes, in preference order, that carry the title as a `t=` param.
_SHARE_ATTRS = (
    "data-share-twitter-url",
    "data-share-facebook-url",
    "data-share-pinterest-url",
    "data-share-email-url",
)


def _title_from_share(el) -> str:
    """Decode the offer title from a data-share-*-url `t=` query param.

    DealNews does not render the title as text on the offer element; it only
    appears URL-encoded in the share links (e.g. ...?s=twitter&t=Ray-Ban%2C...).
    """
    for attr in _SHARE_ATTRS:
        value = el.get(attr)
        if not value:
            continue
        query = parse_qs(urlparse(value).query)
        t = query.get("t")
        if t and t[0].strip():
            return unquote(t[0]).strip()
    return ""


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

            # Offers carry their data on an action <button>; non-OFFER content
            # cards (articles/guides) share the markup but a different type.
            for el in soup.select('[data-content-id][data-content-type="OFFER"]'):
                offer_id = (el.get("data-content-id") or "").strip()
                title = _title_from_share(el)
                # Skip malformed offers missing a stable id or title. Two id-less
                # offers would both get source_id "" and collide on the
                # UNIQUE(source, source_id) upsert, silently overwriting each
                # other. Mirror reddit's guard: a bad offer yields zero rows.
                if not offer_id or not title:
                    continue

                # data-offer-url is absolute on DealNews; fall back to the
                # listing URL if a row somehow lacks it.
                deal_url = (el.get("data-offer-url") or "").strip() or url

                deals.append(
                    RawDeal(
                        source="slickdeals",
                        source_id=offer_id,
                        title=title,
                        url=deal_url,
                        description=None,
                        raw_location=None,
                        posted_at=None,
                        expires_at=None,
                        raw={"content_id": offer_id, "listing_url": url},
                    )
                )
        except Exception:
            # One bad listing URL is skipped, not fatal.
            continue
    return deals
