from typing import List, Optional, Dict, Any, Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError

from ..models.hardware import Hardware
from ..models.category import Category
from ..models.use_case import UseCase
from ..models.software import Software

# Raised when a unique-name constraint is violated 
class DuplicateError(Exception):
    pass

# Raised when the requested row does not exist
class NotFoundError(Exception):
    pass

# Raised when an association references a name that doesn't exist in its lookup table
class UnknownReferenceError(Exception):
    def __init__(self, kind: str, missing: List[str]):
        super().__init__(f"Unknown {kind}: {missing}")
        self.kind = kind
        self.missing = missing


HARDWARE_FIELDS = (
    "operate_temperature",
    "input_power",
    "ip_rating",
    "ik_rating",
    "interface",
    "extra_specs",
)


class AdminRepository:

    def __init__(self, db: Session):
        self.db = db

    # Hardware

    def list_hardware(self) -> Sequence[Hardware]:
        stmt = (
            select(Hardware)
            .where(Hardware.is_active.is_(True))
            .order_by(Hardware.model_name)
        )
        return self.db.execute(stmt).scalars().all()

    def get_hardware(self, model_name: str) -> Optional[Hardware]:
        stmt = (
            select(Hardware)
            .where(Hardware.model_name == model_name, Hardware.is_active.is_(True))
            .options(
                selectinload(Hardware.categories),
                selectinload(Hardware.use_cases),
                selectinload(Hardware.software),
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_hardware_including_inactive(self, model_name: str) -> Optional[Hardware]:
        stmt = select(Hardware).where(Hardware.model_name == model_name)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_hardware(
        self,
        *,
        model_name: str,
        fields: Dict[str, Any],
        categories: List[str],
        use_cases: List[str],
        software: List[str],
    ) -> Hardware:
        if self.get_hardware_including_inactive(model_name) is not None:
            raise DuplicateError(f"Hardware '{model_name}' already exists")

        cat_rows = self._resolve_existing(Category, categories, kind="category")
        uc_rows = self._resolve_existing(UseCase, use_cases, kind="use_case")
        sw_rows = self._resolve_existing(Software, software, kind="software")

        hw = Hardware(model_name=model_name, is_active=True)
        for f in HARDWARE_FIELDS:
            if f in fields:
                setattr(hw, f, fields[f])
        hw.categories = cat_rows
        hw.use_cases = uc_rows
        hw.software = sw_rows

        self.db.add(hw)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise DuplicateError(f"Hardware '{model_name}' already exists")
        self.db.refresh(hw)
        return hw

    def update_hardware(
        self,
        model_name: str,
        *,
        new_model_name: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
        categories: Optional[List[str]] = None,
        use_cases: Optional[List[str]] = None,
        software: Optional[List[str]] = None,
    ) -> Hardware:
        hw = self.get_hardware(model_name)
        if hw is None:
            raise NotFoundError(f"Hardware '{model_name}' not found")

        if new_model_name and new_model_name != model_name:
            collision = self.get_hardware_including_inactive(new_model_name)
            if collision is not None:
                raise DuplicateError(f"Hardware '{new_model_name}' already exists")
            hw.model_name = new_model_name

        if fields:
            for f in HARDWARE_FIELDS:
                if f in fields:
                    setattr(hw, f, fields[f])

        if categories is not None:
            hw.categories = self._resolve_existing(Category, categories, kind="category")
        if use_cases is not None:
            hw.use_cases = self._resolve_existing(UseCase, use_cases, kind="use_case")
        if software is not None:
            hw.software = self._resolve_existing(Software, software, kind="software")

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise DuplicateError(f"Hardware '{new_model_name or model_name}' already exists")
        self.db.refresh(hw)
        return hw

    def soft_delete_hardware(self, model_name: str) -> None:
        hw = self.get_hardware(model_name)
        if hw is None:
            raise NotFoundError(f"Hardware '{model_name}' not found")
        hw.is_active = False
        self.db.commit()

    def list_categories(self) -> Sequence[Category]:
        return self.db.execute(select(Category).order_by(Category.name)).scalars().all()

    def list_use_cases(self) -> Sequence[UseCase]:
        return self.db.execute(select(UseCase).order_by(UseCase.name)).scalars().all()

    def list_software(self) -> Sequence[Software]:
        return self.db.execute(select(Software).order_by(Software.name)).scalars().all()

    def create_category(self, name: str) -> Category:
        return self._create_reference(Category, name, kind="category")

    def create_use_case(self, name: str) -> UseCase:
        return self._create_reference(UseCase, name, kind="use_case")

    def create_software(self, name: str) -> Software:
        return self._create_reference(Software, name, kind="software")

    def rename_category(self, name: str, new_name: str) -> Category:
        return self._rename_reference(Category, name, new_name, kind="category")

    def rename_use_case(self, name: str, new_name: str) -> UseCase:
        return self._rename_reference(UseCase, name, new_name, kind="use_case")

    def rename_software(self, name: str, new_name: str) -> Software:
        return self._rename_reference(Software, name, new_name, kind="software")

    def delete_category(self, name: str) -> None:
        self._delete_reference(Category, name, kind="category")

    def delete_use_case(self, name: str) -> None:
        self._delete_reference(UseCase, name, kind="use_case")

    def delete_software(self, name: str) -> None:
        self._delete_reference(Software, name, kind="software")

    # Helper methods

    def _resolve_existing(self, model, names: List[str], *, kind: str):
        if not names:
            return []
        clean = [n.strip() for n in names if n and n.strip()]
        if not clean:
            return []
        rows = (
            self.db.execute(select(model).where(model.name.in_(clean)))
            .scalars()
            .all()
        )
        found = {r.name for r in rows}
        missing = [n for n in clean if n not in found]
        if missing:
            raise UnknownReferenceError(kind, missing)
        return list(rows)

    def _create_reference(self, model, name: str, *, kind: str):
        clean = (name or "").strip()
        if not clean:
            raise ValueError(f"{kind} name is required")
        existing = (
            self.db.execute(select(model).where(model.name.ilike(clean)))
            .scalar_one_or_none()
        )
        if existing is not None:
            raise DuplicateError(f"{kind} '{clean}' already exists")
        row = model(name=clean)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise DuplicateError(f"{kind} '{clean}' already exists")
        self.db.refresh(row)
        return row

    def _rename_reference(self, model, name: str, new_name: str, *, kind: str):
        row = self.db.execute(select(model).where(model.name == name)).scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"{kind} '{name}' not found")
        clean = (new_name or "").strip()
        if not clean:
            raise ValueError(f"{kind} name is required")
        if clean.lower() == name.lower():
            return row
        collision = self.db.execute(
            select(model).where(model.name.ilike(clean))
        ).scalar_one_or_none()
        if collision is not None and collision.id != row.id:
            raise DuplicateError(f"{kind} '{clean}' already exists")
        row.name = clean
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise DuplicateError(f"{kind} '{clean}' already exists")
        self.db.refresh(row)
        return row

    def _delete_reference(self, model, name: str, *, kind: str) -> None:
        row = self.db.execute(select(model).where(model.name == name)).scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"{kind} '{name}' not found")
        # ON DELETE CASCADE - see backend/db_scripts/00_schema.sql.
        self.db.delete(row)
        self.db.commit()

    #-----Start of software table----
    def create_software_with_extra_fields(self, name: str, extra_fields: Optional[Dict[str, Any]] = None):
        clean = (name or "").strip()
    
        if not clean:
            raise ValueError("software name is required")
    
        existing = self.db.execute(
            select(Software).where(Software.name.ilike(clean))
        ).scalar_one_or_none()
    
        if existing is not None:
            raise DuplicateError(f"software '{clean}' already exists")
    
        software = Software(
            name=clean,
            extra_fields=extra_fields or {}
        )
    
        self.db.add(software)
    
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise DuplicateError(f"software '{clean}' already exists")
    
        self.db.refresh(software)
        return software

    def update_software(self, name: str, *, new_name: Optional[str] = None, extra_fields: Optional[Dict[str, Any]] = None):
        software = self.db.execute(
            select(Software).where(Software.name == name)
        ).scalar_one_or_none()
    
        if software is None:
            raise NotFoundError(f"software '{name}' not found")
    
        if new_name:
            clean_new_name = new_name.strip()
    
            if not clean_new_name:
                raise ValueError("software name is required")
    
            collision = self.db.execute(
                select(Software).where(Software.name.ilike(clean_new_name))
            ).scalar_one_or_none()
    
            if collision is not None and collision.id != software.id:
                raise DuplicateError(f"software '{clean_new_name}' already exists")
    
            software.name = clean_new_name
    
        if extra_fields is not None:
            current = software.extra_fields or {}

            software.extra_fields = {
                **current,
                **extra_fields
            }
    
        self.db.commit()
        self.db.refresh(software)
        return software

    def delete_software_extra_field(self, name: str, field_name: str) -> Software:
        software = self.db.execute(
            select(Software).where(Software.name == name)
        ).scalar_one_or_none()
    
        if software is None:
            raise NotFoundError(f"software '{name}' not found")
    
        current = software.extra_fields or {}
    
        if field_name not in current:
            raise NotFoundError(f"extra field '{field_name}' not found for software '{name}'")
    
        new_fields = dict(current)
        del new_fields[field_name]
    
        software.extra_fields = new_fields
    
        self.db.commit()
        self.db.refresh(software)
        return software
        
