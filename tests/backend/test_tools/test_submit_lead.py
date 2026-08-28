"""
Tests for backend.agent.tools.submit_lead.

Mocks LeadService and email service to avoid real DB/email calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.agent.tools.submit_lead import submit_lead
from backend.engine.state_machine import ConversationSession


class TestSubmitLead:
    """submit_lead should save lead data and enforce the once-per-session guard."""

    @patch("backend.agent.tools.submit_lead.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.submit_lead.get_email_service")
    def test_submit_with_name_and_email(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Submitting with name and email should succeed."""
        mock_save_lead.return_value = {"id": 1, "status": "new"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")
        result = submit_lead(name="Alice", email="alice@example.com", session=session)

        assert result["status"] == "submitted"
        assert result["lead_id"] == 1
        assert session.lead_submitted is True

    @patch("backend.agent.tools.submit_lead.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.submit_lead.get_email_service")
    def test_submit_with_all_fields(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Submitting with all optional fields should succeed."""
        mock_save_lead.return_value = {"id": 2, "status": "new"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")
        result = submit_lead(
            name="Bob",
            email="bob@example.com",
            company="ACME Corp",
            phone="555-0123",
            session=session,
        )

        assert result["status"] == "submitted"
        assert session.lead_submitted is True
        # submit_lead creates its own CollectedInfo — it doesn't modify session.collected_info directly
        # Verify the data was passed to the lead service instead (collected is positional arg 0)
        call_args = mock_save_lead.call_args
        collected = call_args.args[0] if call_args.args else call_args.kwargs.get("collected")
        assert collected.lead.name == "Bob"
        assert collected.lead.email == "bob@example.com"
        assert collected.lead.company == "ACME Corp"
        assert collected.lead.phone == "555-0123"

    @patch("backend.agent.tools.submit_lead.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.submit_lead.get_email_service")
    def test_guard_prevents_double_submit(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Calling submit_lead twice should fail with 'already_submitted'."""
        mock_save_lead.return_value = {"id": 3, "status": "new"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")

        # First submit succeeds
        result1 = submit_lead(name="Alice", email="alice@example.com", session=session)
        assert result1["status"] == "submitted"

        # Second submit fails
        result2 = submit_lead(name="Alice", email="alice@example.com", session=session)
        assert result2["status"] == "already_submitted"

    @patch("backend.agent.tools.submit_lead.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.submit_lead.get_email_service")
    def test_empty_session_still_submits(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """submit_lead should work even without a session (no guard)."""
        mock_save_lead.return_value = {"id": 4, "status": "new"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        result = submit_lead(name="Alice", email="alice@example.com", session=None)

        assert result["status"] == "submitted"

    @patch("backend.agent.tools.submit_lead.LeadService.save_lead_from_collected")
    def test_database_error_handled(self, mock_save_lead: MagicMock):
        """Database errors should return error status."""
        mock_save_lead.side_effect = Exception("DB connection failed")

        session = ConversationSession(id="test")
        result = submit_lead(name="Alice", email="alice@example.com", session=session)

        assert result["status"] == "error"
        assert "DB connection failed" in result["message"]
        # Session should NOT be marked as submitted on error
        assert session.lead_submitted is False

    @patch("backend.agent.tools.submit_lead.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.submit_lead.get_email_service")
    def test_preserves_existing_qualification(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Existing qualification info should be preserved when submitting lead."""
        mock_save_lead.return_value = {"id": 5, "status": "new"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")
        session.collected_info.environment.vertical = "parking"
        session.collected_info.technical_context.card_types = ["contactless"]

        result = submit_lead(name="Alice", email="alice@example.com", session=session)

        assert result["status"] == "submitted"
        # submit_lead creates its own CollectedInfo and merges session data into it
        call_args = mock_save_lead.call_args
        collected = call_args.args[0] if call_args.args else call_args.kwargs.get("collected")
        assert collected.lead.name == "Alice"
        assert collected.environment.vertical == "parking"
        assert collected.technical_context.card_types == ["contactless"]
