"""
capture_lead_info tool — passively captures contact info during conversation.

The agent uses this silently when the customer volunteers their name, email,
company, or phone. Not for proactive asking — the agent asks naturally, and
this tool captures what's shared.
"""

from typing import Any, Dict

from ...engine.state_machine import ConversationSession


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
        if name and not lead.name:
            lead.name = name.strip()
            captured.append("name")
        if email and not lead.email:
            lead.email = email.strip()
            captured.append("email")
        if company and not lead.company:
            lead.company = company.strip()
            captured.append("company")
        if phone and not lead.phone:
            lead.phone = phone.strip()
            captured.append("phone")

    if not captured:
        return {"status": "no_new_info", "captured": []}

    return {
        "status": "captured",
        "captured": captured,
        "_note": "Do NOT announce this to the customer. Continue the conversation naturally.",
    }
