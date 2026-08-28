from typing import Any, Dict, Optional

from ..db.repositories.lead_repository import LeadRepository
from ..db.session import SessionLocal
from ..engine.state_machine import CollectedInfo


class LeadService:
    """Simple service to store leads from conversations."""

    @staticmethod
    def save_lead(
        name: Optional[str] = None,
        email: Optional[str] = None,
        company: Optional[str] = None,
        phone: Optional[str] = None,
        qualification: Optional[Dict[str, Any]] = None,
        products_shown: Optional[Dict[str, Any]] = None,
        status: str = "new",
    ) -> Dict[str, Any]:
        """Store a lead in the database."""
        db = SessionLocal()
        try:
            repo = LeadRepository(db)
            lead = repo.create_lead(
                name=name,
                email=email,
                company=company,
                phone=phone,
                qualification=qualification,
                products_shown=products_shown,
                status=status,
            )
            return {
                "id": lead.id,
                "status": lead.status,
                "message": "Lead saved successfully.",
            }
        finally:
            db.close()

    @staticmethod
    def save_lead_from_collected(
        collected: CollectedInfo,
        products_shown: Optional[Dict[str, Any]] = None,
        status: str = "new",
    ) -> Dict[str, Any]:
        """Extract lead info from CollectedInfo and save."""
        return LeadService.save_lead(
            name=collected.lead.name,
            email=collected.lead.email,
            company=collected.lead.company,
            phone=collected.lead.phone,
            qualification=collected.model_dump(exclude_none=True),
            products_shown=products_shown,
            status=status,
        )


_service_instance = LeadService()


def get_lead_service() -> LeadService:
    return _service_instance
