"""
Shared fixtures for the eval suite (tests/evals/).

Unlike tests/backend/, these tests make real OpenAI calls through the actual
agent loop — no mocking of the LLM. They check model *behavior* (did it pick
the right tool, did it ground its answer in real data, did it avoid a price),
which unit tests structurally cannot verify since they mock the model away.

Opt-in only: skipped unless RUN_EVALS=1 is set, so they never run in normal
`pytest tests/backend` invocations or in CI by accident. Costs real API
tokens — run deliberately with `RUN_EVALS=1 pytest tests/evals`.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_EVALS"):
        return
    skip = pytest.mark.skip(reason="Eval suite is opt-in — set RUN_EVALS=1 to run (real API calls, real cost).")
    for item in items:
        item.add_marker(skip)


@pytest.fixture
def db_session():
    """A fresh in-memory SQLite session with all tables created — same
    approach as tests/backend/conftest.py's db_session fixture."""
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
    session.info["sessionmaker"] = TestSessionLocal
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def patch_direct_db_access(db_session, monkeypatch):
    """Redirect session_scope()'s SessionLocal to the in-memory eval DB, so
    the agent's real tools (search_products, get_product_details, ...) read
    the seeded catalog below instead of the real Postgres DB."""
    test_sessionmaker = db_session.info["sessionmaker"]
    monkeypatch.setattr("backend.db.session.SessionLocal", test_sessionmaker)
    return test_sessionmaker


@pytest.fixture
def seeded_catalog(db_session, patch_direct_db_access):
    """A small but realistic catalog spanning outdoor/indoor and several
    interfaces, so recommendation-correctness assertions have something
    real to check against."""
    from backend.db.repositories.admin_repository import AdminRepository

    admin = AdminRepository(db_session)
    admin.create_category("Parking")
    admin.create_category("Retail")
    admin.create_use_case("Parking Payment Systems")
    admin.create_use_case("Vending Payment Systems")

    admin.create_hardware(
        model_name="VP7200",
        fields={
            "input_power": "5V 2A",
            "interface": "Ethernet, RS232, UART, USB-C & Cellular/LTE (Optional)",
            "operate_temperature": "-30C to 70C",
            "ip_rating": "IP65",
            "ik_rating": "IK07",
            # These words drive the product query's standalone/PIN matching.
            "extra_specs": {"note": "outdoor standalone kiosk terminal with CPU and RAM, Keypad PIN entry, display"},
        },
        categories=["Parking"],
        use_cases=["Parking Payment Systems"],
        software=[],
    )
    admin.create_hardware(
        model_name="VP3300",
        fields={
            "input_power": "USB",
            "interface": "USB",
            "operate_temperature": "0C to 40C",
            "ip_rating": None,
            "extra_specs": {"note": "compact indoor desktop reader"},
        },
        categories=["Retail"],
        use_cases=[],
        software=[],
    )
    admin.create_hardware(
        model_name="VP6300",
        fields={
            "input_power": "5V",
            "interface": "WiFi, Cellular, USB",
            "operate_temperature": "-20C to 65C",
            "ip_rating": "IP54",
            "extra_specs": {"note": "portable handheld reader with WiFi and Cellular"},
        },
        categories=["Retail"],
        use_cases=[],
        software=[],
    )
    return db_session
