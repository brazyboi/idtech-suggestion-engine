"""
Tests for backend.agent.tools.capture_lead_info.

Tests the passive lead info capture — the agent calls this silently when
the customer volunteers contact info during conversation.
"""

from __future__ import annotations

import pytest

from backend.agent.tools.capture_lead_info import capture_lead_info
from backend.engine.state_machine import CollectedInfo, ConversationSession


class TestCaptureLeadInfo:
    """capture_lead_info should passively capture lead fields without overwriting."""

    def test_capture_name(self):
        """Capturing a name should set it on the session."""
        session = ConversationSession(id="test")
        result = capture_lead_info(name="Alice", session=session)
        assert result["status"] == "captured"
        assert "name" in result["captured"]
        assert session.collected_info.lead.name == "Alice"

    def test_capture_email(self):
        """Capturing an email should set it."""
        session = ConversationSession(id="test")
        result = capture_lead_info(email="alice@example.com", session=session)
        assert result["status"] == "captured"
        assert "email" in result["captured"]
        assert session.collected_info.lead.email == "alice@example.com"

    def test_capture_company(self):
        """Capturing a company should set it."""
        session = ConversationSession(id="test")
        result = capture_lead_info(company="ACME Corp", session=session)
        assert result["status"] == "captured"
        assert "company" in result["captured"]
        assert session.collected_info.lead.company == "ACME Corp"

    def test_capture_phone(self):
        """Capturing a phone number should set it."""
        session = ConversationSession(id="test")
        result = capture_lead_info(phone="555-0123", session=session)
        assert result["status"] == "captured"
        assert "phone" in result["captured"]
        assert session.collected_info.lead.phone == "555-0123"

    def test_capture_multiple_fields(self):
        """Capturing multiple fields at once should set all of them."""
        session = ConversationSession(id="test")
        result = capture_lead_info(
            name="Alice",
            email="alice@example.com",
            company="ACME Corp",
            session=session,
        )
        assert result["status"] == "captured"
        assert len(result["captured"]) == 3
        assert session.collected_info.lead.name == "Alice"
        assert session.collected_info.lead.email == "alice@example.com"
        assert session.collected_info.lead.company == "ACME Corp"

    def test_does_not_overwrite_existing_name(self):
        """If a field is already set, it should NOT be overwritten."""
        session = ConversationSession(id="test")
        session.collected_info.lead.name = "Alice"
        result = capture_lead_info(name="Bob", session=session)
        assert result["status"] == "no_new_info"  # Nothing new captured
        assert session.collected_info.lead.name == "Alice"  # Still Alice

    def test_does_not_overwrite_existing_email(self):
        """If email is already set, it should NOT be overwritten."""
        session = ConversationSession(id="test")
        session.collected_info.lead.email = "alice@example.com"
        result = capture_lead_info(email="bob@example.com", session=session)
        assert "email" not in result.get("captured", [])
        assert session.collected_info.lead.email == "alice@example.com"

    def test_no_session_returns_no_new_info(self):
        """If no session is provided, it should return no_new_info."""
        result = capture_lead_info(name="Alice")
        assert result["status"] == "no_new_info"

    def test_captures_new_fields_while_skipping_existing(self):
        """If name exists but email doesn't, only email should be captured."""
        session = ConversationSession(id="test")
        session.collected_info.lead.name = "Alice"
        result = capture_lead_info(
            name="Bob",  # Already set — should be skipped
            email="alice@example.com",  # New — should be captured
            session=session,
        )
        assert result["status"] == "captured"
        assert "email" in result["captured"]
        assert "name" not in result["captured"]
        assert session.collected_info.lead.name == "Alice"  # Not overwritten
        assert session.collected_info.lead.email == "alice@example.com"  # New

    def test_strips_whitespace(self):
        """Values should be stripped of leading/trailing whitespace."""
        session = ConversationSession(id="test")
        result = capture_lead_info(name="  Alice  ", session=session)
        assert session.collected_info.lead.name == "Alice"

    def test_capture_empty_string(self):
        """Empty strings should be treated as new info and set (empty)."""
        session = ConversationSession(id="test")
        # Set name to something first
        session.collected_info.lead.name = "Alice"
        # Try to capture empty string
        result = capture_lead_info(name="", session=session)
        # Empty string is truthy in Python after strip? Let's check: "".strip() == ""
        # So the condition `if name and not lead.name` — name is "" which is falsy
        # So it should be no_new_info
        assert result["status"] == "no_new_info"
        assert session.collected_info.lead.name == "Alice"  # Unchanged

    def test_response_has_note_field(self):
        """The response should include a note telling the agent not to announce."""
        session = ConversationSession(id="test")
        result = capture_lead_info(name="Alice", session=session)
        assert "_note" in result
        assert "Do NOT announce" in result["_note"]
