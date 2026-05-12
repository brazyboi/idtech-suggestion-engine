from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base
from .associations import hardware_category_map, hardware_use_case_map, hardware_software_map

if TYPE_CHECKING:
    from .category import Category
    from .use_case import UseCase
    from .software import Software

class Hardware(Base):
    __tablename__ = "hardware"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    operate_temperature: Mapped[Optional[str]] = mapped_column(String(100))
    input_power: Mapped[Optional[str]] = mapped_column(String(100))
    ip_rating: Mapped[Optional[str]] = mapped_column(String(50))
    ik_rating: Mapped[Optional[str]] = mapped_column(String(50))
    interface: Mapped[Optional[str]] = mapped_column(String(255))
    extra_specs: Mapped[Optional[dict]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    # Many-to-Many Relationships
    categories: Mapped[List["Category"]] = relationship(
        secondary=hardware_category_map, backref="hardware"
    )
    use_cases: Mapped[List["UseCase"]] = relationship(
        secondary=hardware_use_case_map, backref="hardware"
    )
    software: Mapped[List["Software"]] = relationship(
        secondary=hardware_software_map, backref="hardware"
    )

    def __repr__(self) -> str:
        return f"Hardware(id={self.id}, model_name='{self.model_name}')"
