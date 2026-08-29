"""
Tests for backend.engine.conversation_store (conversation persistence across
restarts / multiple worker processes).

The interface tests run against both InMemoryConversationStore and
RedisConversationStore (backed by fakeredis, so no real Redis server is
needed) via a parametrized fixture, since routers/chat.py must see
identical behavior from either implementation.
"""

import time

import fakeredis
import pytest
import redis

from backend.engine.conversation_store import (
    ConversationStore,
    InMemoryConversationStore,
    RedisConversationStore,
    _build_store,
)
import backend.engine.conversation_store as cs_module
from backend.engine.state_machine import ConversationSession


@pytest.fixture(params=["memory", "redis"])
def store(request) -> ConversationStore:
    if request.param == "memory":
        return InMemoryConversationStore()
    return RedisConversationStore(fakeredis.FakeStrictRedis(decode_responses=True))


# ── Interface parity across both implementations ────────────────────────

class TestConversationStoreInterface:
    def test_ensure_session_creates_new_id_when_none_given(self, store):
        sid = store.ensure_session(None)
        assert sid
        assert store.has_session(sid)

    def test_ensure_session_reuses_given_id(self, store):
        sid = store.ensure_session("my-session")
        assert sid == "my-session"
        assert store.ensure_session("my-session") == "my-session"

    def test_has_session_false_for_unknown_id(self, store):
        assert store.has_session("does-not-exist") is False

    def test_get_session_on_unknown_id_returns_a_fresh_session(self, store):
        session = store.get_session("brand-new-id")
        assert session.id == "brand-new-id"
        assert session.history == []

    def test_save_then_get_round_trips_mutations(self, store):
        sid = store.ensure_session(None)
        session = store.get_session(sid)
        session.turn_count = 5
        session.history.append({"role": "user", "content": "hi"})
        store.save_session(sid, session)

        reloaded = store.get_session(sid)
        assert reloaded.turn_count == 5
        assert reloaded.history == [{"role": "user", "content": "hi"}]

    def test_set_fields_round_trip_as_sets_not_lists(self, store):
        """
        asked_slots / answered_slots are Set[str]. JSON has no set type, so
        this is the single most likely place for a silent breakage in the
        Redis path (model_dump_json -> model_validate_json round trip).
        """
        sid = store.ensure_session(None)
        session = store.get_session(sid)
        session.asked_slots.add("vertical")
        session.answered_slots.add("vertical")
        session.answered_slots.add("indoor_outdoor")
        store.save_session(sid, session)

        reloaded = store.get_session(sid)
        assert reloaded.asked_slots == {"vertical"}
        assert isinstance(reloaded.asked_slots, set)
        assert reloaded.answered_slots == {"vertical", "indoor_outdoor"}
        assert isinstance(reloaded.answered_slots, set)

    def test_session_expires_after_ttl(self, store, monkeypatch):
        monkeypatch.setattr(cs_module, "SESSION_TTL_SECONDS", 1)
        sid = store.ensure_session(None)
        assert store.has_session(sid) is True
        time.sleep(1.5)
        assert store.has_session(sid) is False


class TestInMemoryStoreSpecifics:
    def test_get_session_returns_a_copy_not_shared_state(self):
        """Unlike Redis (which always deserializes a fresh object), the
        in-memory store must explicitly deep-copy, or a caller mutating
        the returned session before calling save_session() would corrupt
        the stored session for every other concurrent reader."""
        store = InMemoryConversationStore()
        sid = store.ensure_session(None)

        session = store.get_session(sid)
        session.turn_count = 99  # mutate the copy, never saved

        reloaded = store.get_session(sid)
        assert reloaded.turn_count == 0


# ── Redis-down degradation (must serve the turn, never 500) ─────────────

class _BrokenRedis:
    """Stand-in for a redis.Redis client whose connection is down."""

    def get(self, *a, **kw):
        raise redis.ConnectionError("connection refused")

    def exists(self, *a, **kw):
        raise redis.ConnectionError("connection refused")

    def set(self, *a, **kw):
        raise redis.ConnectionError("connection refused")

    def expire(self, *a, **kw):
        raise redis.ConnectionError("connection refused")


class TestRedisDownDegradesGracefully:
    def test_has_session_returns_false(self):
        store = RedisConversationStore(_BrokenRedis())
        assert store.has_session("some-id") is False

    def test_get_session_returns_a_fresh_session(self):
        store = RedisConversationStore(_BrokenRedis())
        session = store.get_session("some-id")
        assert session.id == "some-id"
        assert session.history == []

    def test_save_session_does_not_raise(self):
        store = RedisConversationStore(_BrokenRedis())
        store.save_session("some-id", ConversationSession(id="some-id"))

    def test_ensure_session_still_returns_an_id(self):
        store = RedisConversationStore(_BrokenRedis())
        sid = store.ensure_session(None)
        assert sid


# ── get_conversation_store() selection ──────────────────────────────────

class TestStoreSelection:
    def test_selects_in_memory_when_redis_url_unset(self, monkeypatch):
        monkeypatch.setattr(cs_module, "REDIS_URL", None)
        assert isinstance(_build_store(), InMemoryConversationStore)

    def test_selects_redis_when_redis_url_set(self, monkeypatch):
        monkeypatch.setattr(cs_module, "REDIS_URL", "redis://localhost:6379/0")
        assert isinstance(_build_store(), RedisConversationStore)
