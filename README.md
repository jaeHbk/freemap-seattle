# FreeMap Seattle

Scraped free/BOGO deals. Physical deals on a Leaflet map; online (and
failed-geocode physical) deals in a list. Seattle-first, region-agnostic
(metro is config). Anonymous read-only browse, no accounts.

Architecture: Python scrapers -> SQLite -> read-only FastAPI -> vanilla-JS
Leaflet frontend. All correctness lives in `scrapers/pipeline.py` (shared
contract ETL). The scraper layer is decoupled so it can run unattended via
`meshclaw run TASK.md` on cron with zero secrets.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the tests

```bash
pytest
```

See `docs/superpowers/specs/2026-06-18-freemap-seattle-design.md` for the full design.
