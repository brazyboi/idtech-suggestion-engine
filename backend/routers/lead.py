from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.repositories.event_repository import EventRepository
from backend.db.repositories.lead_repository import LeadRepository
from backend.db.session import get_db
from backend.engine.lead_service import LeadService, get_lead_service

router = APIRouter()


class FunnelMetrics(BaseModel):
    sessions_started: int
    recommendations_shown: int
    leads_captured: int
    recommendation_rate: Optional[float] = None
    conversion_rate: Optional[float] = None
    close_rate: Optional[float] = None


class RequestCallRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[Dict[str, Any]] = None


class LeadOut(BaseModel):
    id: int
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    qualification: Optional[dict] = None
    products_shown: Optional[dict] = None
    status: str
    created_at: Optional[str] = None


@router.post("/request-call")
async def request_call(
    request: RequestCallRequest,
    lead_service: LeadService = Depends(get_lead_service),
):
    """Accept lead info and trigger a sales follow-up."""
    result = lead_service.save_lead(
        name=request.name,
        email=request.email,
        company=request.company,
        phone=request.phone,
        qualification=request.qualification,
        status="requested_call",
    )
    return {
        "success": True,
        "message": "Thanks! A sales rep will reach out to you shortly.",
        "lead_id": result["id"],
    }


@router.get("/leads", response_model=List[LeadOut])
async def list_leads(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List all leads, most recent first."""
    repo = LeadRepository(db)
    leads = repo.list_leads(limit=limit, offset=offset)
    return [
        LeadOut(
            id=lead.id,
            name=lead.name,
            email=lead.email,
            company=lead.company,
            phone=lead.phone,
            qualification=lead.qualification,
            products_shown=lead.products_shown,
            status=lead.status,
            created_at=lead.created_at.isoformat() if lead.created_at else None,
        )
        for lead in leads
    ]


@router.get("/metrics", response_model=FunnelMetrics)
async def get_funnel_metrics(db: Session = Depends(get_db)):
    """
    Resolution-rate view for the admin dashboard: how many conversations
    started, how many got as far as a recommendation, and how many
    converted to a captured lead (submit_lead or escalate_to_sales).
    """
    counts = EventRepository(db).funnel_counts()
    started = counts["session_started"]
    shown = counts["recommendation_shown"]
    captured = counts["lead_submitted"]

    return FunnelMetrics(
        sessions_started=started,
        recommendations_shown=shown,
        leads_captured=captured,
        recommendation_rate=(shown / started) if started else None,
        conversion_rate=(captured / started) if started else None,
        close_rate=(captured / shown) if shown else None,
    )


@router.get("/leads/{lead_id}", response_model=LeadOut)
async def get_lead(lead_id: int, db: Session = Depends(get_db)):
    """Get a single lead by ID."""
    repo = LeadRepository(db)
    lead = repo.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadOut(
        id=lead.id,
        name=lead.name,
        email=lead.email,
        company=lead.company,
        phone=lead.phone,
        qualification=lead.qualification,
        products_shown=lead.products_shown,
        status=lead.status,
        created_at=lead.created_at.isoformat() if lead.created_at else None,
    )