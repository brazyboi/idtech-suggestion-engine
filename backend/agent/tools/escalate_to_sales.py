"""
escalate_to_sales tool — immediately flags for human follow-up.

Used when the customer asks to speak to someone, has a complex question,
or is frustrated. Submits lead with escalation flag and sends urgent email.
"""

from typing import Any, Dict

from ...engine.lead_service import LeadService
from ...engine.state_machine import CollectedInfo, ConversationSession
from ...services.email import get_email_service


def escalate_to_sales(
    reason: str,
    name: str | None = None,
    email: str | None = None,
    session: ConversationSession | None = None,
) -> Dict[str, Any]:
    """
    Escalate the conversation to a sales rep.

    Submits whatever contact info is available and flags as urgent.

    Returns a confirmation message for the customer.
    """
    # Build best-effort lead info
    customer_name = name or "Unknown"
    customer_email = email or "not_provided@unknown.com"

    collected = CollectedInfo()
    collected.lead.name = customer_name
    collected.lead.email = customer_email

    if session:
        existing = session.collected_info
        if existing.environment.vertical:
            collected.environment = existing.environment
        collected.transaction_profile = existing.transaction_profile
        collected.technical_context = existing.technical_context
        if existing.lead.company:
            collected.lead.company = existing.lead.company
        if existing.lead.phone:
            collected.lead.phone = existing.lead.phone

    # Save with escalation flag
    try:
        result = LeadService.save_lead_from_collected(
            collected,
            status="escalated",
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}

    # Send urgent email
    email_svc = get_email_service()
    email_svc.send_lead_notification(
        lead_name=customer_name,
        lead_email=customer_email,
        company=session.collected_info.lead.company if session else None,
        qualification=collected.model_dump(exclude_none=True),
        is_escalation=True,
    )

    if session:
        session.lead_submitted = True

    return {
        "status": "escalated",
        "lead_id": result.get("id"),
        "message": (
            f"I've flagged your inquiry as urgent, {customer_name}. "
            f"A senior sales rep will reach out within a few hours. "
            f"Reason noted: {reason}"
        ),
    }
