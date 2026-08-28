"""
Tests for backend.agent.slot_extractor.

Uses unittest.mock to avoid real OpenAI API calls.

Important: the slot_extractor uses a module-level singleton (_extractor) that
is created at import time. We patch the singleton's client.chat.completions.create
method directly rather than patching the OpenAI constructor.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.agent.slot_extractor import _extractor
from backend.engine.state_machine import CollectedInfo


def _setup_mock_extractor(mock_create: MagicMock, data: dict) -> None:
    """Configure the mock create() to return a specific JSON extraction."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(data)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_create.return_value = mock_response


class TestSlotExtractor:
    """extract_slots should extract fields from messages into CollectedInfo."""

    def test_extract_vertical(self):
        """Extracting 'parking' should set environment.vertical."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"vertical": "parking"})
            collected = CollectedInfo()
            new_info = _extractor.extract("we're a parking lot", collected)

        assert new_info.get("vertical") == "parking"
        assert collected.environment.vertical == "parking"

    def test_extract_indoor_outdoor(self):
        """Extracting 'outdoor' should set environment.indoor_outdoor."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"indoor_outdoor": "outdoor"})
            collected = CollectedInfo()
            new_info = _extractor.extract("it's for outdoor use", collected)

        assert new_info.get("indoor_outdoor") == "outdoor"
        assert collected.environment.indoor_outdoor == "outdoor"

    def test_extract_card_types(self):
        """Extracting card types should set technical_context.card_types."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"card_types": ["contactless", "chip"]})
            collected = CollectedInfo()
            new_info = _extractor.extract("we accept tap and chip", collected)

        assert "card_types" in new_info
        assert collected.technical_context.card_types == ["contactless", "chip"]

    def test_extract_needs_pin_true(self):
        """Extracting 'yes' for PIN should set needs_pin=True."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"needs_pin": "yes"})
            collected = CollectedInfo()
            new_info = _extractor.extract("yes we need PIN entry", collected)

        assert new_info.get("needs_pin") is True
        assert collected.technical_context.needs_pin is True

    def test_extract_needs_pin_false(self):
        """Extracting 'no' for PIN should set needs_pin=False."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"needs_pin": "no"})
            collected = CollectedInfo()
            new_info = _extractor.extract("no PIN needed", collected)

        assert new_info.get("needs_pin") is False
        assert collected.technical_context.needs_pin is False

    def test_extract_name(self):
        """Extracting a name should set lead.name."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"name": "Alice"})
            collected = CollectedInfo()
            new_info = _extractor.extract("my name is Alice", collected)

        assert new_info.get("name") == "Alice"
        assert collected.lead.name == "Alice"

    def test_extract_email(self):
        """Extracting an email should set lead.email."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"email": "alice@example.com"})
            collected = CollectedInfo()
            new_info = _extractor.extract("you can reach me at alice@example.com", collected)

        assert new_info.get("email") == "alice@example.com"
        assert collected.lead.email == "alice@example.com"

    def test_extract_monthly_volume(self):
        """Extracting volume should set transaction_profile.monthly_volume."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"monthly_volume": 5000})
            collected = CollectedInfo()
            new_info = _extractor.extract("about 5000 transactions per month", collected)

        assert new_info.get("monthly_volume") == 5000
        assert collected.transaction_profile.monthly_volume == 5000

    def test_does_not_overwrite_existing(self):
        """If a field is already set, it should NOT be overwritten."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"vertical": "retail"})
            collected = CollectedInfo()
            collected.environment.vertical = "parking"  # Already set
            new_info = _extractor.extract("we're a retail store", collected)

        assert "vertical" not in new_info  # Should not be returned as new
        assert collected.environment.vertical == "parking"  # Should not be overwritten

    def test_partial_update(self):
        """Only new fields should be filled, existing ones preserved."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {
                "vertical": "retail",       # Already set — should be skipped
                "indoor_outdoor": "indoor",  # New — should be set
            })
            collected = CollectedInfo()
            collected.environment.vertical = "retail"
            new_info = _extractor.extract("we're an indoor retail store", collected)

        assert "vertical" not in new_info
        assert new_info.get("indoor_outdoor") == "indoor"
        assert collected.environment.vertical == "retail"
        assert collected.environment.indoor_outdoor == "indoor"

    def test_api_error_returns_empty(self):
        """API errors should not crash and return empty dict."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            mock_create.side_effect = Exception("API error")
            collected = CollectedInfo()
            new_info = _extractor.extract("hello", collected)

        assert new_info == {}

    def test_empty_json_response(self):
        """Empty JSON response should return empty dict."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {})
            collected = CollectedInfo()
            new_info = _extractor.extract("hello", collected)

        assert new_info == {}

    def test_boolean_conversion_from_string(self):
        """String 'true'/'yes' should convert to boolean True."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"is_standalone": "true"})
            collected = CollectedInfo()
            new_info = _extractor.extract("it's a standalone device", collected)

        assert new_info.get("is_standalone") is True
        assert collected.technical_context.is_standalone is True

    def test_boolean_conversion_false_string(self):
        """String 'false' should convert to boolean False."""
        with patch.object(_extractor.client.chat.completions, "create") as mock_create:
            _setup_mock_extractor(mock_create, {"is_standalone": "false"})
            collected = CollectedInfo()
            new_info = _extractor.extract("it connects to a host", collected)

        assert new_info.get("is_standalone") is False
        assert collected.technical_context.is_standalone is False
