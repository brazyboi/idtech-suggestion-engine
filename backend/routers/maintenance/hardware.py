from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...db.repositories.admin_repository import (
    AdminRepository,
    DuplicateError,
    NotFoundError,
    UnknownReferenceError,
)
from ...db.models.hardware import Hardware
from .schemas import (
    HardwareCreate,
    HardwareUpdate,
    HardwareOut,
    HardwareSummary,
)

router = APIRouter(tags=["maintenance:hardware"])

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


# @router.get("", response_model=List[HardwareSummary])
# def list_hardware(db: Session = Depends(get_db)):
#     repo = AdminRepository(db)
#     return repo.list_hardware()


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


# from fastapi import APIRouter, Depends, HTTPException
# from pydantic import BaseModel
from sqlalchemy import select
# from sqlalchemy.orm import Session
# from typing import Optional

@router.get("/")
def get_all_hardware(db: Session = Depends(get_db)):
    try:
        stmt = select(
            Hardware.id,
            Hardware.model_name,
            Hardware.is_active,
            Hardware.operate_temperature,
            Hardware.input_power,
            Hardware.ip_rating,
            Hardware.ik_rating,
            Hardware.interface,
        ).order_by(Hardware.model_name)
        rows = db.execute(stmt).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"ERROR in get_all_hardware: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# class HardwareCreate(BaseModel):
#     model_name: str
#     operate_temperature: Optional[str] = None
#     input_power: Optional[str] = None
#     ip_rating: Optional[str] = None
#     ik_rating: Optional[str] = None
#     interface: Optional[str] = None

# @router.get("/")
# def get_all_hardware(db: Session = Depends(get_db)):
#     try:
#         stmt = select(
#             Hardware.id,
#             Hardware.model_name,
#             Hardware.operate_temperature,
#             Hardware.input_power,
#             Hardware.ip_rating,
#             Hardware.ik_rating,
#             Hardware.interface,
#         ).order_by(Hardware.model_name)
#         rows = db.execute(stmt).mappings().all()
#         return [dict(r) for r in rows]
#     except Exception as e:
#         print(f"ERROR in get_all_hardware: {type(e).__name__}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.post("/", status_code=201)
# def add_hardware(payload: HardwareCreate, db: Session = Depends(get_db)):
#     try:
#         device = Hardware(
#             model_name=payload.model_name,
#             operate_temperature=payload.operate_temperature or None,
#             input_power=payload.input_power or None,
#             ip_rating=payload.ip_rating or None,
#             ik_rating=payload.ik_rating or None,
#             interface=payload.interface or None,
#         )
#         db.add(device)
#         db.commit()
#         db.refresh(device)
#         return {"id": device.id, "model_name": device.model_name}
#     except Exception as e:
#         db.rollback()
#         print(f"ERROR in add_hardware: {type(e).__name__}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.delete("/{device_id}", status_code=200)
# def delete_hardware(device_id: int, db: Session = Depends(get_db)):
#     try:
#         device = db.get(Hardware, device_id)
#         if device is None:
#             raise HTTPException(status_code=404, detail="Device not found")
#         db.delete(device)
#         db.commit()
#         return {"deleted_id": device_id}
#     except HTTPException:
#         raise
#     except Exception as e:
#         db.rollback()
#         print(f"ERROR in delete_hardware: {type(e).__name__}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))
