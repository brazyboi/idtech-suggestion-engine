"""
Shared test fixtures for the backend test suite.

Adds the project root to sys.path so absolute imports (backend.xxx) resolve.
Provides pre-built sample sessions, CollectedInfo instances, and mock data.
"""

import sys
import os
from typing import Any, Dict, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add project root to sys.path so `from backend.xxx import yyy` works
_project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Tests mock OpenAI, so provide a harmless key when none is configured.
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-pytest")

# Tests use an in-memory SQLite database.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# Tests only need fixed local values for admin and session authentication.
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-for-pytest")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-for-pytest")

from backend.engine.state_machine import (
    CollectedInfo,
    ConversationSession,
    EnvironmentInfo,
    TechnicalContext,
    TransactionProfile,
    LeadInfo,
)


# ── Database fixtures (in-memory SQLite, isolated per test) ────────────
#
# SQLite is a fast substitute for these repository and API tests.

@pytest.fixture
def db_session():
    """A fresh in-memory SQLite session with all tables created."""
    from backend.db.base import Base
    import backend.db.models  # noqa: F401 - registers all model classes on Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSessionLocal()
    session.info["sessionmaker"] = TestSessionLocal  # exposed for patch_direct_db_access
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def patch_direct_db_access(db_session, monkeypatch):
    """
    Several modules (lead_service, search_products, get_product_details,
    product_matcher) call `session_scope()` directly instead of going through
    FastAPI's `get_db` dependency, so overriding `get_db` alone does not
    redirect them to the test DB. `session_scope()` opens sessions via the
    single `SessionLocal` in backend.db.session, so patching it there once
    (rather than at every import site) is enough to redirect all of them to
    the same in-memory engine as `db_session`.
    """
    test_sessionmaker = db_session.info["sessionmaker"]
    monkeypatch.setattr("backend.db.session.SessionLocal", test_sessionmaker)
    return test_sessionmaker


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """
    backend.rate_limit.limiter (see D3 in ARCHITECTURE.md) is a module-level
    singleton shared by the whole process, including every test. Without
    resetting it between tests, request counts would accumulate across
    the suite and unrelated tests would start failing with 429s once the
    cumulative count crossed a limit.
    """
    from backend.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def api_client(db_session):
    """
    A FastAPI TestClient wired to the in-memory SQLite session via a
    get_db override, so router tests never touch the real Postgres DB.

    Carries the admin API key by default (see D1 in ARCHITECTURE.md —
    /api/lead/* and /api/maintenance/* now require it), so existing tests
    that exercise those endpoints don't each need to pass it explicitly.
    Auth-specific tests use `unauthed_api_client` instead.
    """
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.db.session import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app, headers={"X-Admin-Api-Key": os.environ["ADMIN_API_KEY"]})
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def unauthed_api_client(db_session):
    """Same as api_client but with no admin key header, for testing the D1 auth gate."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.db.session import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _make_collected(**overrides) -> CollectedInfo:
    """
    Helper to create a CollectedInfo with safety-pin fields set via overrides.
    
    Usage: _make_collected(environment__vertical="parking")
    translates to:  c.environment.vertical = "parking"
    """
    c = CollectedInfo()
    for key, value in overrides.items():
        if "__" in key:
            section, field = key.split("__", 1)
            sub = getattr(c, section, None)
            if sub is not None:
                setattr(sub, field, value)
        else:
            setattr(c, key, value)
    return c


# ── Sample CollectedInfo Fixtures ───────────────────────────────────────

@pytest.fixture
def empty_collected() -> CollectedInfo:
    """A freshly-created CollectedInfo with all defaults."""
    return CollectedInfo()


@pytest.fixture
def greeting_collected() -> CollectedInfo:
    """CollectedInfo in the greeting stage — only use case known."""
    c = CollectedInfo()
    c.environment.vertical = "parking"
    return c


@pytest.fixture
def qualifying_collected() -> CollectedInfo:
    """CollectedInfo in the qualifying stage — has use case + some environment."""
    c = CollectedInfo()
    c.environment.vertical = "parking"
    c.environment.indoor_outdoor = "outdoor"
    c.technical_context.card_types = ["contactless"]
    c.technical_context.needs_pin = True
    return c


@pytest.fixture
def recommending_collected() -> CollectedInfo:
    """CollectedInfo ready for recommendations — has all qualifying info but no recommendations shown yet."""
    c = CollectedInfo()
    c.environment.vertical = "parking"
    c.environment.indoor_outdoor = "outdoor"
    c.technical_context.card_types = ["contactless", "chip"]
    c.technical_context.needs_pin = True
    c.technical_context.is_standalone = True
    c.technical_context.power_source = "VAC"
    return c


@pytest.fixture
def lead_capture_collected() -> CollectedInfo:
    """CollectedInfo after recommendations shown, needs lead info."""
    c = CollectedInfo()
    c.environment.vertical = "parking"
    c.environment.indoor_outdoor = "outdoor"
    c.technical_context.card_types = ["contactless"]
    c.technical_context.needs_pin = True
    c.technical_context.is_standalone = True
    c.technical_context.power_source = "VAC"
    c.meta.recommendation_shown = True
    return c


@pytest.fixture
def complete_collected() -> CollectedInfo:
    """CollectedInfo with everything including lead info."""
    c = CollectedInfo()
    c.environment.vertical = "parking"
    c.environment.indoor_outdoor = "outdoor"
    c.technical_context.card_types = ["contactless"]
    c.technical_context.needs_pin = True
    c.technical_context.is_standalone = True
    c.technical_context.power_source = "VAC"
    c.lead.name = "Alice"
    c.lead.email = "alice@example.com"
    c.meta.recommendation_shown = True
    return c


@pytest.fixture
def empty_session(empty_collected: CollectedInfo) -> ConversationSession:
    """A fresh session with no collected info."""
    return ConversationSession(
        id="test-session-empty",
        collected_info=empty_collected,
    )


@pytest.fixture
def qualifying_session(qualifying_collected: CollectedInfo) -> ConversationSession:
    """Session in the qualifying stage."""
    return ConversationSession(
        id="test-session-qualifying",
        collected_info=qualifying_collected,
    )


@pytest.fixture
def recommending_session(recommending_collected: CollectedInfo) -> ConversationSession:
    """Session ready for recommendation stage."""
    return ConversationSession(
        id="test-session-recommending",
        collected_info=recommending_collected,
    )


@pytest.fixture
def lead_capture_session(lead_capture_collected: CollectedInfo) -> ConversationSession:
    """Session in lead capture stage."""
    return ConversationSession(
        id="test-session-lead-capture",
        collected_info=lead_capture_collected,
    )


@pytest.fixture
def complete_session(complete_collected: CollectedInfo) -> ConversationSession:
    """Session with lead submitted."""
    return ConversationSession(
        id="test-session-complete",
        collected_info=complete_collected,
        lead_submitted=True,
    )


@pytest.fixture
def sample_products() -> List[Dict[str, Any]]:
    """Sample product data matching the search_products return format."""
    return [
        {
            "model_name": "VP3300",
            "compatible_software": ["IDTECH IDPar"],
            "highlights": ["Power: USB", "Interface: USB", "Temp: 0°C to 40°C"],
            "key_specs": {
                "input_power": "USB",
                "interface": "USB",
                "operate_temperature": "0°C to 40°C",
                "ip_rating": "IP54",
                "ik_rating": None,
            },
        },
        {
            "model_name": "VP5300",
            "compatible_software": ["IDTECH IDPar"],
            "highlights": ["Power: USB", "Interface: USB", "Temp: -20°C to 65°C"],
            "key_specs": {
                "input_power": "USB",
                "interface": "USB",
                "operate_temperature": "-20°C to 65°C",
                "ip_rating": "IP65",
                "ik_rating": None,
            },
        },
    ]
