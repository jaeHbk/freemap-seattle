"""Canonical Free/BOGO scope detection shared by sources and the pipeline."""

from __future__ import annotations

import re

_BOGO = re.compile(
    r"\b(?:bogo|b1g1)\b|\bbuy\s+one\b.{0,80}\bget\s+one\b",
    re.IGNORECASE | re.DOTALL,
)
_FREE = re.compile(
    r"\b(?:free|freebie|giveaway)\b|\bgiving\s+away\b",
    re.IGNORECASE,
)


def classify_deal_type(title: str, description: str | None = None) -> str:
    """Return bogo, free, or other without substring false positives."""
    text = f"{title} {description or ''}"
    if _BOGO.search(text):
        return "bogo"
    if _FREE.search(text):
        return "free"
    return "other"


def is_target_deal(title: str, description: str | None = None) -> bool:
    """Whether text is in FreeMap's Free/BOGO product scope."""
    return classify_deal_type(title, description) != "other"
