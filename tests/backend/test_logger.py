"""
Tests for backend.services.logger.

Tests the ReasoningTrace reasoning logger used by the agentic loop.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from backend.services.logger import ReasoningTrace


class TestReasoningTrace:
    """ReasoningTrace should record step-by-step agent decisions."""

    def test_creation(self):
        """A trace should start with the given turn_id and no steps."""
        trace = ReasoningTrace(turn_id="turn-0")
        assert trace.turn_id == "turn-0"
        assert trace.steps == []

    def test_intent_classified(self):
        """intent_classified should add a step."""
        trace = ReasoningTrace(turn_id="turn-0")
        trace.intent_classified("product_search", 0.95, {"model": "VP3300"})
        assert len(trace.steps) == 1
        step = trace.steps[0]
        assert step["kind"] == "intent_classification"
        assert step["intent"] == "product_search"
        assert step["confidence"] == 0.95

    def test_tool_called(self):
        """tool_called should add a step."""
        trace = ReasoningTrace(turn_id="turn-0")
        trace.tool_called("search_products", {"use_case": "parking"})
        assert len(trace.steps) == 1
        step = trace.steps[0]
        assert step["kind"] == "tool_call"
        assert step["tool"] == "search_products"
        assert step["arguments"] == {"use_case": "parking"}

    def test_tool_result(self):
        """tool_result should add a step."""
        trace = ReasoningTrace(turn_id="turn-0")
        trace.tool_result("search_products", "Found 2 products", success=True)
        assert len(trace.steps) == 1
        step = trace.steps[0]
        assert step["kind"] == "tool_result"
        assert step["tool"] == "search_products"
        assert step["success"] is True

    def test_response_generated(self):
        """response_generated should add a step with a truncated text preview."""
        trace = ReasoningTrace(turn_id="turn-0")
        trace.response_generated("recommendation", "Based on your requirements I recommend the VP3300...")
        assert len(trace.steps) == 1
        step = trace.steps[0]
        assert step["kind"] == "response"
        assert step["type"] == "recommendation"

    def test_response_truncated_to_200_chars(self):
        """Text preview should be truncated to 200 characters."""
        trace = ReasoningTrace(turn_id="turn-0")
        long_text = "A" * 500
        trace.response_generated("clarification", long_text)
        step = trace.steps[0]
        assert len(step["text_preview"]) == 200

    def test_full_flow(self):
        """A full trace should contain all steps in order."""
        trace = ReasoningTrace(turn_id="turn-0")
        trace.intent_classified("product_search", 0.95, {})
        trace.tool_called("search_products", {"use_case": "retail"})
        trace.tool_result("search_products", "Found 1 product", success=True)
        trace.response_generated("recommendation", "I recommend the VP3300.")

        assert len(trace.steps) == 4
        assert trace.steps[0]["kind"] == "intent_classification"
        assert trace.steps[1]["kind"] == "tool_call"
        assert trace.steps[2]["kind"] == "tool_result"
        assert trace.steps[3]["kind"] == "response"

    def test_to_dict_contains_metadata(self):
        """to_dict should include turn_id, elapsed_ms, and steps."""
        trace = ReasoningTrace(turn_id="turn-0")
        trace.intent_classified("greeting", 1.0, {})
        d = trace.to_dict()
        assert d["turn_id"] == "turn-0"
        assert "elapsed_ms" in d
        assert d["elapsed_ms"] >= 0
        assert len(d["steps"]) == 1

    def test_log_to_console_does_not_crash(self):
        """log_to_console should not raise exceptions."""
        trace = ReasoningTrace(turn_id="turn-0")
        trace.intent_classified("faq", 1.0, {})
        # Should not raise
        trace.log_to_console()
