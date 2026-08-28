"""
Shared test fixtures for the backend test suite.

Adds the project root to sys.path so absolute imports (backend.xxx) resolve.
Provides pre-built sample sessions, CollectedInfo instances, and mock data.
"""

import sys
import os
from typing import Any, Dict, List

import pytest

# Add project root to sys.path so `from backend.xxx import yyy` works
_project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.engine.state_machine import (
    CollectedInfo,
    ConversationSession,
    EnvironmentInfo,
    TechnicalContext,
    TransactionProfile,
    LeadInfo,
)


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
