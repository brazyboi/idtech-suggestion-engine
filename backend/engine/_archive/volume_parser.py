"""
Dedicated parser for volume/ticket information.

This is the only deterministic parser we keep in the system.  It handles
a uniquely structured format (e.g. "1000 transactions, $10 each") that the
LLM finds surprisingly error-prone.  All other extraction is done by the
LLM through constrained per-slot tools.
"""

from typing import Any, Dict

from .input_parsers import parse_volume_ticket


class VolumeTicketParser:
    """
    Parses user messages for volume/ticket information using a regex parser.

    Returns a dict with structure:
        {"transaction_profile": {"monthly_volume": int, "average_ticket": float}}
    """

    @staticmethod
    def parse(message: str) -> Dict[str, Any]:
        """
        Parse a user message for volume/ticket data.

        Args:
            message: The raw user message text.

        Returns:
            A dict with transaction_profile data, or empty dict if nothing
            could be parsed.
        """
        result: Dict[str, Any] = {}
        vt = parse_volume_ticket(message)
        if vt:
            if "monthly_volume" in vt and vt["monthly_volume"] is not None:
                result.setdefault("transaction_profile", {})["monthly_volume"] = vt["monthly_volume"]
            if "average_ticket" in vt and vt["average_ticket"] is not None:
                result.setdefault("transaction_profile", {})["average_ticket"] = vt["average_ticket"]
        return result
