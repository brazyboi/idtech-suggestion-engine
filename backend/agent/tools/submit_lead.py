"""
submit_lead tool — submits contact info to sales team.

Wraps LeadService.save_lead_from_collected() and sends email notification.
Guard: only callable once per session.
"""

from typing import Any, Dict

from ...engine.lead_service import LeadService
from ...engine.state_machine import CollectedInfo, ConversationSession
from ...services.email import get_email_service


def submit_lead(
    name: str,
    email: str,
    company: str | None = None,
    phone: str | None = None,
    session: ConversationSession | None = None,
) -> Dict[str, Any]:
    """
    Submit the customer's contact information for sales follow-up.

    Only callable once per session — subsequent calls return an error.

    Returns a confirmation dict.
    """
    if session and session.lead_submitted:
        return {
            "status": "already_submitted",
            "message": "Lead was already submitted for this session.",
        }

    # Build CollectedInfo with lead data
    collected = CollectedInfo()
    collected.lead.name = name
    collected.lead.email = email
    if company:
        collected.lead.company = company
    if phone:
        collected.lead.phone = phone

    # If session has existing collected_info, merge it
    if session:
        existing = session.collected_info
        if existing.environment.vertical:
            collected.environment = existing.environment
        collected.transaction_profile = existing.transaction_profile
        collected.technical_context = existing.technical_context

    # Save to database
    try:
        result = LeadService.save_lead_from_collected(
            collected,
            products_shown={
                "products": session.recommended_products if session else [],
            },
            status="new",
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}

    # Send email notification
    email_svc = get_email_service()
    email_svc.send_lead_notification(
        lead_name=name,
        lead_email=email,
        company=company,
        phone=phone,
        qualification=collected.model_dump(exclude_none=True),
        products_shown={"products": session.recommended_products} if session else None,
        is_escalation=False,
    )

    # Mark session
    if session:
        session.lead_submitted = True

    return {
        "status": "submitted",
        "lead_id": result.get("id"),
        "message": (
            f"Thanks, {name}! Your information has been sent to our sales team. "
            f"A sales rep will follow up with you at {email} within 1-2 business days."
        ),
    }
