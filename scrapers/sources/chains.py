"""chains source: parse a multi-location restaurant group's happy-hours page into
one physical RawDeal per venue. Wired to Tom Douglas Restaurants
(https://www.tomdouglas.com/happy-hour/), a server-rendered BentoBox page whose
robots.txt allows it and which needs no secrets.

Each happy hour is hosted at a NAMED PHYSICAL SEATTLE VENUE (Half Shell, Palace
Kitchen, Neb, Serious Pie, ...), so every deal carries a raw_location the pipeline
geocodes to a map pin — the value the online-only live sources (slickdeals, local)
don't provide.

Markup shape: the page has no per-offer data attributes, so we anchor on the
stable signal — each venue block ends in a "Visit" call-to-action rendered as
`<a class="btn-brand" href="https://<venue-site>/...">`. The venue NAME is the
nearest preceding <h2> and the blurb the nearest preceding <p>. Intro/footer
"Visit"/"See All" buttons use a RELATIVE href (e.g. /our-restaurants/), so we keep
only anchors whose href has a network location (absolute, off-site). Reads
config.user_agent and config.sources["chains"] (offers_urls + venues address map)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from scrapers.config import Config
from scrapers.contract import RawDeal


def _venue_location(name: str, venues: dict) -> str:
    """Resolve a venue name to a geocodable address.

    Prefer the configured address (precise, stable); fall back to a
    "<venue>, Seattle, WA" string so a newly-added venue still surfaces as a
    physical deal (Nominatim resolves most named Seattle restaurants by name).
    """
    return venues.get(name) or f"{name}, Seattle, WA"


def fetch(config: Config) -> list[RawDeal]:
    settings = config.sources.get("chains", {})
    offers_urls: list[str] = settings.get("offers_urls", [])
    venues: dict = settings.get("venues", {})
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

            # Dedup within a single page: the same venue can carry more than one
            # "Visit" button (e.g. a duplicated CTA), and two deals sharing a
            # source_id would collide on the UNIQUE(source, source_id) upsert and
            # silently overwrite each other.
            seen_ids: set[str] = set()

            # Walk <h2>/<p>/<a> in document order, pairing each off-site "Visit"
            # link with the most recent UNCONSUMED <h2> (the venue name) and <p>
            # (the blurb) that precede it. Document-order traversal — rather than
            # link.find_previous("h2") — is what makes a name-less offer block
            # skip correctly: the real page's mis-nested markup means a bare
            # find_previous would walk past the block boundary and wrongly reuse
            # the prior venue's heading. Consuming the heading prevents that.
            current_name = ""
            current_desc: str | None = None
            heading_used = True  # nothing to consume until the first <h2>

            for el in soup.find_all(["h2", "p", "a"]):
                if el.name == "h2":
                    current_name = el.get_text(strip=True)
                    current_desc = None
                    heading_used = False
                    continue
                if el.name == "p":
                    # Remember the first <p> after the heading as the blurb.
                    if current_desc is None:
                        current_desc = el.get_text(" ", strip=True)
                    continue

                # el is an <a>: only off-site "Visit" CTAs name a venue deal.
                classes = el.get("class") or []
                if "btn-brand" not in classes:
                    continue
                href = (el.get("href") or "").strip()
                # Skip intro/footer nav buttons: those use a RELATIVE href (no
                # network location). A real venue block links off-site to the
                # venue's own happy-hour menu.
                if not urlparse(href).netloc:
                    continue
                # Skip a CTA with no preceding (unconsumed) venue heading. This is
                # the name-less / already-paired block guard — mirror the other
                # sources: a malformed block yields zero deals rather than a deal
                # titled "" or one reusing a neighbour's name.
                if heading_used or not current_name:
                    continue

                # The off-site Visit URL is a stable, unique id per venue block
                # (one happy hour per venue page). Distinct venues sharing a host
                # (e.g. two Serious Pie locations on seriouspieseattle.com) keep
                # distinct paths, so the full URL stays unique.
                source_id = href
                heading_used = True
                if source_id in seen_ids:
                    continue
                seen_ids.add(source_id)

                name = current_name
                description = current_desc

                deals.append(
                    RawDeal(
                        source="chains",
                        source_id=source_id,
                        title=f"{name} Happy Hour",
                        url=href,
                        description=description,
                        raw_location=_venue_location(name, venues),
                        posted_at=None,
                        expires_at=None,
                        raw={
                            "venue": name,
                            "venue_url": href,
                            "offers_url": url,
                        },
                    )
                )
        except Exception:
            # One bad offers URL is skipped, not fatal.
            continue
    return deals
