from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...db.repositories.admin_repository import (
    AdminRepository,
    DuplicateError,
    NotFoundError,
)
from .schemas import ReferenceItem, ReferenceCreate

router = APIRouter(prefix="/maintenance", tags=["maintenance:references"])

def _handle_create(call):
    try:
        return call()
    except DuplicateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

def _handle_rename(call):
    try:
        return call()
    except NotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except DuplicateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

def _handle_delete(call):
    try:
        call()
    except NotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))

@router.get("/categories", response_model=List[ReferenceItem])
def list_categories(db: Session = Depends(get_db)):
    return AdminRepository(db).list_categories()

@router.post("/categories", response_model=ReferenceItem, status_code=status.HTTP_201_CREATED)
def create_category(payload: ReferenceCreate, db: Session = Depends(get_db)):
    return _handle_create(lambda: AdminRepository(db).create_category(payload.name))

@router.patch("/categories/{name}", response_model=ReferenceItem)
def rename_category(name: str, payload: ReferenceCreate, db: Session = Depends(get_db)):
    return _handle_rename(lambda: AdminRepository(db).rename_category(name, payload.name))

@router.delete("/categories/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(name: str, db: Session = Depends(get_db)):
    _handle_delete(lambda: AdminRepository(db).delete_category(name))

@router.get("/use-cases", response_model=List[ReferenceItem])
def list_use_cases(db: Session = Depends(get_db)):
    return AdminRepository(db).list_use_cases()

@router.post("/use-cases", response_model=ReferenceItem, status_code=status.HTTP_201_CREATED)
def create_use_case(payload: ReferenceCreate, db: Session = Depends(get_db)):
    return _handle_create(lambda: AdminRepository(db).create_use_case(payload.name))

@router.patch("/use-cases/{name}", response_model=ReferenceItem)
def rename_use_case(name: str, payload: ReferenceCreate, db: Session = Depends(get_db)):
    return _handle_rename(lambda: AdminRepository(db).rename_use_case(name, payload.name))

@router.delete("/use-cases/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_use_case(name: str, db: Session = Depends(get_db)):
    _handle_delete(lambda: AdminRepository(db).delete_use_case(name))

@router.get("/software", response_model=List[ReferenceItem])
def list_software(db: Session = Depends(get_db)):
    return AdminRepository(db).list_software()

@router.post("/software", response_model=ReferenceItem, status_code=status.HTTP_201_CREATED)
def create_software(payload: ReferenceCreate, db: Session = Depends(get_db)):
    return _handle_create(lambda: AdminRepository(db).create_software(payload.name))

@router.patch("/software/{name}", response_model=ReferenceItem)
def rename_software(name: str, payload: ReferenceCreate, db: Session = Depends(get_db)):
    return _handle_rename(lambda: AdminRepository(db).rename_software(name, payload.name))

@router.delete("/software/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_software(name: str, db: Session = Depends(get_db)):
    _handle_delete(lambda: AdminRepository(db).delete_software(name))


# from fastapi import APIRouter, Depends, HTTPException
# from pydantic import BaseModel
# from sqlalchemy import select
# from sqlalchemy.orm import Session
# from typing import Optional
# from ...db.session import get_db
# from ...db.models.software import Software

# router = APIRouter()

# class SoftwareCreate(BaseModel):
#     software_name: str

# # these sample endpoints will be replaced with soft deletion
# @router.get("/")
# def get_all_software(db: Session = Depends(get_db)):
#     try:
#         stmt = select(
#             Software.id,
#             Software.name,
#         ).order_by(Software.name)
#         rows = db.execute(stmt).mappings().all()
#         return [dict(r) for r in rows]
#     except Exception as e:
#         print(f"ERROR in get_all_software: {type(e).__name__}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.post("/", status_code=201)
# def add_software(payload: SoftwareCreate, db: Session = Depends(get_db)):
#     try:
#         software = Software(
#             name=payload.software_name
#         )
#         db.add(software)
#         db.commit()
#         db.refresh(software)
#         return {"id": software.id, "name": software.name}
#     except Exception as e:
#         db.rollback()
#         print(f"ERROR in add_software: {type(e).__name__}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

# @router.delete("/{software_id}", status_code=200)
# def delete_software(software_id: int, db: Session = Depends(get_db)):
#     try:
#         software = db.get(Software, software_id)
#         if software is None:
#             raise HTTPException(status_code=404, detail="Software not found")
#         db.delete(software)
#         db.commit()
#         return {"deleted_id": software.id}
#     except HTTPException:
#         raise
#     except Exception as e:
#         db.rollback()
#         print(f"ERROR in delete_software: {type(e).__name__}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

