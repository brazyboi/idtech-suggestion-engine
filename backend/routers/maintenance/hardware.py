from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from db.repositories.admin_repository import (
    AdminRepository,
    DuplicateError,
    NotFoundError,
    UnknownReferenceError,
)
from db.models.hardware import Hardware
from .schemas import (
    HardwareCreate,
    HardwareUpdate,
    HardwareOut,
    HardwareSummary,
)

router = APIRouter(prefix="/maintenance/hardware", tags=["maintenance:hardware"])


def _to_out(hw: Hardware) -> HardwareOut:
    return HardwareOut(
        id=hw.id,
        model_name=hw.model_name,
        is_active=hw.is_active,
        operate_temperature=hw.operate_temperature,
        input_power=hw.input_power,
        ip_rating=hw.ip_rating,
        ik_rating=hw.ik_rating,
        interface=hw.interface,
        extra_specs=hw.extra_specs,
        categories=[c.name for c in hw.categories],
        use_cases=[u.name for u in hw.use_cases],
        software=[s.name for s in hw.software],
    )


@router.get("", response_model=List[HardwareSummary])
def list_hardware(db: Session = Depends(get_db)):
    repo = AdminRepository(db)
    return repo.list_hardware()


@router.get("/{model_name}", response_model=HardwareOut)
def get_hardware(model_name: str, db: Session = Depends(get_db)):
    repo = AdminRepository(db)
    hw = repo.get_hardware(model_name)
    if hw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Hardware '{model_name}' not found")
    return _to_out(hw)


@router.post("", response_model=HardwareOut, status_code=status.HTTP_201_CREATED)
def create_hardware(payload: HardwareCreate, db: Session = Depends(get_db)):
    repo = AdminRepository(db)
    fields = payload.model_dump(exclude={"model_name", "categories", "use_cases", "software"})
    try:
        hw = repo.create_hardware(
            model_name=payload.model_name,
            fields=fields,
            categories=payload.categories,
            use_cases=payload.use_cases,
            software=payload.software,
        )
    except DuplicateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except UnknownReferenceError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return _to_out(hw)


@router.patch("/{model_name}", response_model=HardwareOut)
def update_hardware(model_name: str, payload: HardwareUpdate, db: Session = Depends(get_db)):
    repo = AdminRepository(db)
    body = payload.model_dump(exclude_unset=True)
    new_model_name = body.pop("model_name", None)
    categories = body.pop("categories", None)
    use_cases = body.pop("use_cases", None)
    software = body.pop("software", None)

    try:
        hw = repo.update_hardware(
            model_name,
            new_model_name=new_model_name,
            fields=body,
            categories=categories,
            use_cases=use_cases,
            software=software,
        )
    except NotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except DuplicateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except UnknownReferenceError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return _to_out(hw)


@router.delete("/{model_name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_hardware(model_name: str, db: Session = Depends(get_db)):
    repo = AdminRepository(db)
    try:
        repo.soft_delete_hardware(model_name)
    except NotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return None
