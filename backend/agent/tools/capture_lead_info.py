"""
capture_lead_info tool — passively captures contact info during conversation.

The agent uses this silently when the customer volunteers their name, email,
company, or phone. Not for proactive asking — the agent asks naturally, and
this tool captures what's shared.
"""

import re
from typing import Any, Dict

from ...engine.state_machine import ConversationSession

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[\d\s()+\-.]{7,20}$")

# Reject spec terms that the model may mistake for a name or company.
_IMPLAUSIBLE_TERMS = (
    "wifi", "wi-fi", "cellular", "bluetooth", "ethernet", "usb", "nfc",
    "emv", "contactless", "magstripe", "rs232", "serial", "pin pad",
)


def _is_plausible_name_or_company(value: str) -> bool:
    lower = value.lower()
    if "?" in value:
        return False
    return not any(term in lower for term in _IMPLAUSIBLE_TERMS)


def capture_lead_info(
    name: str | None = None,
    email: str | None = None,
    company: str | None = None,
    phone: str | None = None,
    session: ConversationSession | None = None,
) -> Dict[str, Any]:
    """
    Silently capture lead contact information.

    Only captures what's provided — does not ask for missing fields.
    Updates the session's collected_info.lead in-place.

    Returns a confirmation (not shown to the customer).
    """
    captured: list[str] = []

    if session:
        lead = session.collected_info.lead
        if name and not lead.name and _is_plausible_name_or_company(name):
            lead.name = name.strip()
            captured.append("name")
        if email and not lead.email and _EMAIL_RE.match(email.strip()):
            lead.email = email.strip()
            captured.append("email")
        if company and not lead.company and _is_plausible_name_or_company(company):
            lead.company = company.strip()
            captured.append("company")
        if phone and not lead.phone and _PHONE_RE.match(phone.strip()):
            lead.phone = phone.strip()
            captured.append("phone")

    if not captured:
        return {"status": "no_new_info", "captured": []}

    return {
        "status": "captured",
        "captured": captured,
        "_note": "Do NOT announce this to the customer. Continue the conversation naturally.",
    }
