from __future__ import annotations

import abc
import logging
import os
import time
from threading import Lock
from typing import Dict, Optional
import uuid

import redis

from ..engine.state_machine import ConversationSession

logger = logging.getLogger(__name__)

# Bounds session lifetime either way: in-memory evicts lazily on access,
# Redis uses this as native TTL (see ARCHITECTURE.md item C).
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(4 * 60 * 60)))

# Redis shares sessions across workers and restarts; memory storage is for dev/test.
REDIS_URL = os.getenv("REDIS_URL")

# Keep the password separate so it is not exposed in logged connection URLs.
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")


class ConversationStore(abc.ABC):
    """
    Interface for conversation session persistence. routers/chat.py only
    depends on these four methods — implementations are swappable via
    get_conversation_store() based on whether REDIS_URL is configured.
    """

    @abc.abstractmethod
    def ensure_session(self, session_id: Optional[str]) -> str:
        """Return an existing session ID or create a new one."""

    @abc.abstractmethod
    def has_session(self, session_id: str) -> bool:
        """True if session_id refers to a live (non-expired) session."""

    @abc.abstractmethod
    def get_session(self, session_id: str) -> ConversationSession:
        """
        Return a session for safe mutation by the caller, who later calls
        save_session() to persist it back.
        """

    @abc.abstractmethod
    def save_session(self, session_id: str, session: ConversationSession) -> None:
        """Store the (mutated) session back into the store."""

    @abc.abstractmethod
    def ping(self) -> bool:
        """True if the backing store is reachable — used by GET /ready (H4)."""


class InMemoryConversationStore(ConversationStore):
    """
    Process-local session store. Thread-safe via a lock. Sessions idle
    longer than SESSION_TTL_SECONDS are evicted lazily on access.

    Does not survive a restart and is not shared across worker processes
    — kept for local dev/test and as the no-Redis fallback.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: Dict[str, ConversationSession] = {}
        self._last_accessed: Dict[str, float] = {}

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [
            sid for sid, last in self._last_accessed.items()
            if now - last > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._last_accessed.pop(sid, None)

    def ensure_session(self, session_id: Optional[str]) -> str:
        sid = session_id or str(uuid.uuid4())
        with self._lock:
            self._evict_expired()
            if sid not in self._sessions:
                self._sessions[sid] = ConversationSession(id=sid)
            self._last_accessed[sid] = time.monotonic()
        return sid

    def has_session(self, session_id: str) -> bool:
        with self._lock:
            self._evict_expired()
            return session_id in self._sessions

    def get_session(self, session_id: str) -> ConversationSession:
        """Returns a deep copy — the caller mutates it, then calls save_session()."""
        with self._lock:
            self._evict_expired()
            session = self._sessions.setdefault(
                session_id, ConversationSession(id=session_id)
            )
            self._last_accessed[session_id] = time.monotonic()
            return session.model_copy(deep=True)

    def save_session(self, session_id: str, session: ConversationSession) -> None:
        with self._lock:
            self._sessions[session_id] = session
            self._last_accessed[session_id] = time.monotonic()

    def ping(self) -> bool:
        # Nothing external to reach — always up. There's no Redis dependency
        # in this mode, so /ready shouldn't report a fake Redis outage.
        return True


class RedisConversationStore(ConversationStore):
    """
    Redis-backed session store. Key `session:{id}`, value
    `ConversationSession.model_dump_json()`. TTL is native (SET ... EX on
    write, EXPIRE on read) — sliding expiry, replacing the in-memory
    store's manual _evict_expired sweep.

    A dead Redis must not 500 every chat turn: every method catches
    redis.RedisError and degrades to serving the turn with a fresh,
    unpersisted session rather than crashing (degraded-but-up beats
    hard-down for a sales widget).
    """

    def __init__(self, client: "redis.Redis") -> None:
        self._redis = client

    @staticmethod
    def _key(session_id: str) -> str:
        return f"session:{session_id}"

    def ensure_session(self, session_id: Optional[str]) -> str:
        sid = session_id or str(uuid.uuid4())
        if not self.has_session(sid):
            self.save_session(sid, ConversationSession(id=sid))
        return sid

    def has_session(self, session_id: str) -> bool:
        try:
            return bool(self._redis.exists(self._key(session_id)))
        except redis.RedisError:
            logger.error("Redis unreachable in has_session(%s)", session_id, exc_info=True)
            return False

    def get_session(self, session_id: str) -> ConversationSession:
        key = self._key(session_id)
        try:
            raw = self._redis.get(key)
        except redis.RedisError:
            logger.error("Redis unreachable in get_session(%s); serving a fresh session", session_id, exc_info=True)
            return ConversationSession(id=session_id)

        if raw is None:
            return ConversationSession(id=session_id)

        session = ConversationSession.model_validate_json(raw)
        try:
            self._redis.expire(key, SESSION_TTL_SECONDS)
        except redis.RedisError:
            logger.error("Redis unreachable refreshing TTL for %s", session_id, exc_info=True)
        return session

    def save_session(self, session_id: str, session: ConversationSession) -> None:
        try:
            self._redis.set(self._key(session_id), session.model_dump_json(), ex=SESSION_TTL_SECONDS)
        except redis.RedisError:
            logger.error("Redis unreachable in save_session(%s); this turn will not persist", session_id, exc_info=True)

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except redis.RedisError:
            logger.error("Redis unreachable in ping()", exc_info=True)
            return False


def _build_store() -> ConversationStore:
    if REDIS_URL:
        logger.info("ConversationStore: using Redis at %s — sessions persist across restarts and worker processes.", REDIS_URL)
        if not REDIS_PASSWORD:
            logger.warning(
                "ConversationStore: REDIS_PASSWORD is not set — connecting to Redis "
                "without auth. Fine for a local Redis with no exposed port; a "
                "production deploy should set REDIS_PASSWORD (see backend/.env.example)."
            )
        client = redis.from_url(REDIS_URL, password=REDIS_PASSWORD or None, decode_responses=True)
        return RedisConversationStore(client)

    logger.warning(
        "ConversationStore: REDIS_URL is not set — falling back to an in-memory store. "
        "Sessions will NOT survive a restart and will NOT be shared across multiple "
        "worker processes. This is fine for local dev/test; do not run production "
        "traffic this way."
    )
    return InMemoryConversationStore()


_store: ConversationStore = _build_store()


def get_conversation_store() -> ConversationStore:
    return _store
