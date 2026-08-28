from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, or_, String
from ..models.hardware import Hardware
from ..models.software import Software
from ..models.category import Category
from ..models.use_case import UseCase
from typing import List, Optional

class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def find_products(self, 
                      category: Optional[str] = None, 
                      use_case: Optional[str] = None, 
                      input_power: Optional[str] = None,
                      interface: Optional[str] = None,
                      temp: Optional[str] = None,
                      extra_filter: Optional[str] = None,
                      query: Optional[str] = None,
                      is_outdoor: Optional[bool] = None,
                      is_standalone: Optional[bool] = None) -> List[Hardware]:
        """
        Comprehensive search for hardware along with its compatible software.
        """
        # We use joinedload to pre-fetch the software and categories in one go
        stmt = select(Hardware).options(
            joinedload(Hardware.software),
            joinedload(Hardware.categories),
            joinedload(Hardware.use_cases)
        )

        filters = []
        
        if category:
            stmt = stmt.join(Hardware.categories).where(Category.name.ilike(f"%{category}%"))
        
        if use_case:
            stmt = stmt.join(Hardware.use_cases).where(UseCase.name.ilike(f"%{use_case}%"))

        if input_power:
            # Broaden search to include extra_specs and voltage patterns
            power_val = input_power.upper()
            power_filters = [
                Hardware.input_power.ilike(f"%{input_power}%"),
                Hardware.extra_specs.cast(String).ilike(f"%{input_power}%"),
                Hardware.input_power.is_(None) # Allow NULL if power is requested
            ]
            
            # Handle VAC/AC synonym
            if "VAC" in power_val or "AC" in power_val:
                power_filters.extend([
                    Hardware.input_power.ilike("%AC%"),
                    Hardware.extra_specs.cast(String).ilike("%AC%")
                ])
                
            # Add VDC/DC/V logic
            if "DC" in power_val or "V" in power_val:
                power_filters.extend([
                    Hardware.input_power.ilike("%DC%"),
                    Hardware.extra_specs.cast(String).ilike("%DC%"),
                    Hardware.input_power.ilike("%V%"), # Match '9V', '24V'
                    Hardware.extra_specs.cast(String).ilike("%V%")
                ])
            
            filters.append(or_(*power_filters))
        
        if interface:
            filters.append(or_(
                Hardware.interface.ilike(f"%{interface}%"),
                Hardware.extra_specs.cast(String).ilike(f"%{interface}%"),
                Hardware.interface.is_(None) # Allow NULL if interface is requested
            ))

        if temp:
            filters.append(or_(
                Hardware.operate_temperature.ilike(f"%{temp}%"),
                Hardware.extra_specs.cast(String).ilike(f"%{temp}%")
            ))

        if extra_filter:
            # Handle comma-separated filters (e.g., "PIN,display")
            tags = [tag.strip() for tag in extra_filter.split(",") if tag.strip()]
            for tag in tags:
                tag_filters = [Hardware.extra_specs.cast(String).ilike(f"%{tag}%")]
                
                # Synonym mapping: PIN -> Keypad/Keys
                if tag.upper() == "PIN":
                    tag_filters.append(Hardware.extra_specs.cast(String).ilike("%Keypad%"))
                    tag_filters.append(Hardware.extra_specs.cast(String).ilike("%Keys%"))
                
                filters.append(or_(*tag_filters))

        if query:
            filters.append(or_(
                Hardware.model_name.ilike(f"%{query}%"),
                Hardware.extra_specs.cast(String).ilike(f"%{query}%")
            ))

        if is_outdoor:
            filters.append(or_(
                Hardware.ip_rating.ilike("%IP%"),
                Hardware.extra_specs.cast(String).ilike("%weather%")
            ))

        if is_standalone:
            filters.append(or_(
                Hardware.extra_specs.cast(String).ilike("%RAM%"),
                Hardware.extra_specs.cast(String).ilike("%CPU%"),
                Hardware.extra_specs.cast(String).ilike("%Processor%")
            ))

        if filters:
            from sqlalchemy import and_
            stmt = stmt.where(and_(*filters))

        result = self.db.execute(stmt)
        return result.scalars().unique().all()
