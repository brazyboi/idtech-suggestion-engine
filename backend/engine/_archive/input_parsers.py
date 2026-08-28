"""
Special-purpose parsers preserved because they handle uniquely structured
user input that is painful for the LLM to extract reliably.

Everything else (boolean, choice, number, free-text) is now handled by the
LLM via constrained per-slot tools — the regex parsers for those were
removed because they created an unreliable dual-parser system.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


def parse_volume_ticket(text: str) -> Optional[Dict[str, Any]]:
    """
    Try to parse "1000 transactions, $10 each" style messages.

    Returns dict with monthly_volume and average_ticket if both found,
    or just one if only one is found.
    """
    result: Dict[str, Any] = {}

    # Look for a number followed by optional "transactions" or "/month" or "per month"
    volume_patterns = [
        r'(\d[\d,]*)\s*(?:transactions?|txns?|/month|per month|a month|monthly)',
        r'(?:about|around|approx(?:imately)?)\s*(\d[\d,]*)\s*(?:transactions?|txns?)?',
        r'(\d[\d,]*)\s*(?:transactions?|txns?)',
    ]
    for pat in volume_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                result["monthly_volume"] = int(raw)
            except ValueError:
                pass
            break

    # Look for dollar amounts
    ticket_patterns = [
        r'\$(\d+(?:\.\d{1,2})?)\s*(?:each|per|/|a ticket|average|avg)',
        r'(?:average|avg)(?:\s+ticket)?\s*(?:of|is|:)?\s*\$(\d+(?:\.\d{1,2})?)',
        r'\$(\d+(?:\.\d{1,2})?)',
    ]
    for pat in ticket_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                result["average_ticket"] = float(m.group(1))
            except ValueError:
                pass
            break

    return result if result else None


# Sentinel for "not sure" responses (used by the slot planner)
class _NotSure:
    """Sentinel indicating the user answered 'not sure'."""
    def __bool__(self) -> bool:
        return False
    def __repr__(self) -> str:
        return "NOT_SURE"


NOT_SURE = _NotSure()
