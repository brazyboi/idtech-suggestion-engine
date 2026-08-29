from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ConversationEvent(Base):
    __tablename__ = "conversation_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"ConversationEvent(session_id='{self.session_id}', event_type='{self.event_type}')"
