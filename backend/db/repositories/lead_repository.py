from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.lead import Lead


class LeadRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_lead(
        self,
        name: Optional[str] = None,
        email: Optional[str] = None,
        company: Optional[str] = None,
        phone: Optional[str] = None,
        qualification: Optional[dict] = None,
        products_shown: Optional[dict] = None,
        status: str = "new",
    ) -> Lead:
        """Create a new lead record."""
        lead = Lead(
            name=name,
            email=email,
            company=company,
            phone=phone,
            qualification=qualification,
            products_shown=products_shown,
            status=status,
        )
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def list_leads(self, limit: int = 100, offset: int = 0) -> Sequence[Lead]:
        """List leads ordered by most recent first."""
        stmt = (
            select(Lead)
            .order_by(Lead.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.db.execute(stmt).scalars().all()

    def get_lead(self, lead_id: int) -> Optional[Lead]:
        """Get a single lead by ID."""
        stmt = select(Lead).where(Lead.id == lead_id)
        return self.db.execute(stmt).scalar_one_or_none()