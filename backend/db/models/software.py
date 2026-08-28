from typing import Optional
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base

class Software(Base):
    __tablename__ = "software"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    extra_fields: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"Software(id={self.id}, name='{self.name}')"
