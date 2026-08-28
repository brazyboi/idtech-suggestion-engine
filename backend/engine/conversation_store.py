from __future__ import annotations

from threading import Lock
from typing import Dict
import uuid

from ..engine.state_machine import ConversationSession


class ConversationStore:
    """
    In-memory session store for chat conversations.

    Stores ConversationSession objects (the single source of truth for
    all conversation state). Thread-safe via a lock.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: Dict[str, ConversationSession] = {}

    def ensure_session(self, session_id: str | None) -> str:
        """Return an existing session ID or create a new one."""
        sid = session_id or str(uuid.uuid4())
        with self._lock:
            if sid not in self._sessions:
                self._sessions[sid] = ConversationSession(id=sid)
        return sid

    def get_session(self, session_id: str) -> ConversationSession:
        """
        Return a deep copy of the session for safe mutation.
        The caller mutates the copy, then calls save_session() to persist.
        """
        with self._lock:
            session = self._sessions.setdefault(
                session_id, ConversationSession(id=session_id)
            )
            return session.model_copy(deep=True)

    def save_session(self, session_id: str, session: ConversationSession) -> None:
        """Store the (mutated) session back into the store."""
        with self._lock:
            self._sessions[session_id] = session


_store = ConversationStore()


def get_conversation_store() -> ConversationStore:
    return _store