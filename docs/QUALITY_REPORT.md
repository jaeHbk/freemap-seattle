# Information Quality Report

Measured against commit `a16b310`, before candidate/evidence staging.

## Result

| Measure | Before | After | Evidence |
|---|---:|---:|---|
| Enabled discovery sources | 2 | 5 | `config.toml` |
| Represented source tiers | not tracked | 4 | `deal_candidates.source_tier` |
| Verified official location records | 43 | 44 | committed `places_brand` inventory |
| Official offer families | 4 | 5 | Frye Art Museum added from its official visit page |
| Published categories | 2 | 3 | food, retail, and cultural/event |
| Enforced map-pin floor | 39 | 40 | `[health].minimum_pins` |
| Published policy violations | not measurable | 0 required | `python -m scrapers.quality` |

The deterministic proof scenario stages 48 candidates from all five sources:
44 current official candidates publish, two plausible single-source claims stay
pending, and two ordinary/non-deal claims are rejected. The public result has 44
pins across three categories, a minimum quality score of 100, and zero policy
violations.

Run the proof:

```bash
./.venv/bin/pytest -q \
  tests/test_candidate_staging.py::test_quality_and_breadth_improve_against_committed_baseline
```

Audit any populated database:

```bash
./.venv/bin/python -m scrapers.quality --db db/deals.db
```

## What This Proves

- Broad discovery can retain noisy claims without exposing them to users.
- Every newly published row is in Free/BOGO scope and links to an accepted
  candidate with official or independently corroborated evidence.
- The committed public inventory gains a cultural offer, category, and map pin.
- Scheduled automation fails if a public row bypasses those gates.

## Limitation

The audit proves policy conformance and provenance, not that a source can never
be wrong. Official terms remain subject to 30-day human reverification, and
pending community/editorial/aggregator claims need independent matching evidence
before publication.
