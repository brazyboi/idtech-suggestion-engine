from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.conversation_event import ConversationEvent

FUNNEL_EVENT_TYPES = ("session_started", "recommendation_shown", "lead_submitted")


class EventRepository:
    def __init__(self, db: Session):
        self.db = db

    def log_event(self, session_id: str, event_type: str) -> None:
        """Record a funnel event. Best-effort — callers should not let a
        logging failure break the chat turn that triggered it."""
        self.db.add(ConversationEvent(session_id=session_id, event_type=event_type))
        self.db.commit()

    def funnel_counts(self) -> Dict[str, int]:
        """Distinct sessions that reached each funnel stage at least once."""
        stmt = (
            select(ConversationEvent.event_type, func.count(func.distinct(ConversationEvent.session_id)))
            .where(ConversationEvent.event_type.in_(FUNNEL_EVENT_TYPES))
            .group_by(ConversationEvent.event_type)
        )
        rows = self.db.execute(stmt).all()
        counts = {event_type: 0 for event_type in FUNNEL_EVENT_TYPES}
        counts.update({event_type: count for event_type, count in rows})
        return counts
