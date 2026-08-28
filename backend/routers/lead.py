from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.repositories.lead_repository import LeadRepository
from backend.db.session import get_db
from backend.engine.lead_service import LeadService, get_lead_service

router = APIRouter()


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