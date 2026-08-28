"""
Tests for backend.agent.tools.escalate_to_sales.

Mocks LeadService and email service to avoid real DB/email calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.agent.tools.escalate_to_sales import escalate_to_sales
from backend.engine.state_machine import ConversationSession


class TestEscalateToSales:
    """escalate_to_sales should flag for human follow-up and mark session."""

    @patch("backend.agent.tools.escalate_to_sales.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.escalate_to_sales.get_email_service")
    def test_escalate_with_name_email(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Escalating with name and email should succeed."""
        mock_save_lead.return_value = {"id": 1, "status": "escalated"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")
        result = escalate_to_sales(
            reason="Customer needs a custom integration",
            name="Alice",
            email="alice@example.com",
            session=session,
        )

        assert result["status"] == "escalated"
        assert result["lead_id"] == 1
        assert "urgent" in result["message"].lower()
        assert session.lead_submitted is True

    @patch("backend.agent.tools.escalate_to_sales.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.escalate_to_sales.get_email_service")
    def test_escalate_without_name_email(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Escalating without name/email should fall back to 'Unknown'."""
        mock_save_lead.return_value = {"id": 2, "status": "escalated"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")
        result = escalate_to_sales(
            reason="Complex pricing question",
            name=None,
            email=None,
            session=session,
        )

        assert result["status"] == "escalated"
        assert session.lead_submitted is True

    @patch("backend.agent.tools.escalate_to_sales.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.escalate_to_sales.get_email_service")
    def test_escalate_without_session(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Escalating without a session should still work."""
        mock_save_lead.return_value = {"id": 3, "status": "escalated"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        result = escalate_to_sales(
            reason="Urgent deployment question",
            name="Bob",
            email="bob@example.com",
            session=None,
        )

        assert result["status"] == "escalated"

    @patch("backend.agent.tools.escalate_to_sales.LeadService.save_lead_from_collected")
    def test_db_error_handled(self, mock_save_lead: MagicMock):
        """Database errors should return error status."""
        mock_save_lead.side_effect = Exception("DB connection failed")

        session = ConversationSession(id="test")
        result = escalate_to_sales(
            reason="Technical issue",
            name="Alice",
            email="alice@example.com",
            session=session,
        )

        assert result["status"] == "error"
        assert "DB connection failed" in result["message"]
        assert session.lead_submitted is False  # Not marked on error

    @patch("backend.agent.tools.escalate_to_sales.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.escalate_to_sales.get_email_service")
    def test_preserves_qualification_info(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """Existing qualification info should be carried into the escalation."""
        mock_save_lead.return_value = {"id": 4, "status": "escalated"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")
        session.collected_info.environment.vertical = "parking"
        session.collected_info.transaction_profile.monthly_volume = 5000

        result = escalate_to_sales(
            reason="High volume inquiry",
            name="Alice",
            email="alice@example.com",
            session=session,
        )

        assert result["status"] == "escalated"
        # Verify the collected info was passed through (collected is positional arg 0)
        call_args = mock_save_lead.call_args
        assert call_args is not None
        collected = call_args.args[0] if call_args.args else call_args.kwargs.get("collected")
        assert collected is not None
        assert collected.environment.vertical == "parking"

    @patch("backend.agent.tools.escalate_to_sales.LeadService.save_lead_from_collected")
    @patch("backend.agent.tools.escalate_to_sales.get_email_service")
    def test_reason_included(self, mock_email_svc: MagicMock, mock_save_lead: MagicMock):
        """The reason should appear in the response message."""
        mock_save_lead.return_value = {"id": 5, "status": "escalated"}
        mock_email_instance = MagicMock()
        mock_email_instance.send_lead_notification.return_value = True
        mock_email_svc.return_value = mock_email_instance

        session = ConversationSession(id="test")
        result = escalate_to_sales(
            reason="Customer wants a bespoke solution",
            name="Alice",
            email="alice@example.com",
            session=session,
        )

        assert "bespoke" in result["message"]
