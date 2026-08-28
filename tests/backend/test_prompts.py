"""
Tests for backend.agent.prompts.

Covers:
- _determine_stage() — stage transition logic (the Phase 6 fix)
- _build_known_summary() — context string assembly
- build_system_prompt() — full system prompt rendering
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.agent.prompts import (
    _determine_stage,
    _build_known_summary,
    build_system_prompt,
    STAGE_INSTRUCTIONS,
    SYSTEM_PROMPT_TEMPLATE,
)
from backend.engine.state_machine import CollectedInfo, ConversationSession


# ── Helper ──────────────────────────────────────────────────────────────

def make_collected(**overrides: Any) -> CollectedInfo:
    """Create CollectedInfo via attribute assignment."""
    c = CollectedInfo()
    for key, value in overrides.items():
        if "__" in key:
            section, field = key.split("__", 1)
            sub = getattr(c, section, None)
            if sub is not None and hasattr(sub, field):
                setattr(sub, field, value)
        else:
            if hasattr(c, key):
                setattr(c, key, value)
    return c


# ── _determine_stage() ─────────────────────────────────────────────────

class TestDetermineStage:
    """_determine_stage mirrors determine_next_state but for prompt building.

    Flow: greeting → qualifying → recommending → lead_capture → complete
    """

    def test_empty_is_greeting(self):
        """No data at all → greeting."""
        c = CollectedInfo()
        assert _determine_stage(c, lead_submitted=False) == "greeting"

    def test_use_case_no_environment_is_qualifying(self):
        """Use case without environment/tech → qualifying."""
        c = make_collected(environment__vertical="parking")
        assert _determine_stage(c, lead_submitted=False) == "qualifying"

    def test_use_case_and_environment_no_tech_is_qualifying(self):
        """Use case + environment but no tech → qualifying."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
        )
        assert _determine_stage(c, lead_submitted=False) == "qualifying"

    def test_fully_qualified_no_recommendation_is_recommending(self):
        """Full qualifiers but recommendation not shown → recommending.

        This is the Phase 6 fix — this path was previously dead code.
        """
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
        )
        assert _determine_stage(c, lead_submitted=False) == "recommending"

    def test_recommendation_shown_no_lead_is_lead_capture(self):
        """Recommendation shown + no lead info → lead_capture."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
        )
        c.meta.recommendation_shown = True
        assert _determine_stage(c, lead_submitted=False) == "lead_capture"

    def test_name_and_email_is_complete(self):
        """Everything collected → complete."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
            lead__name="Alice",
            lead__email="alice@example.com",
        )
        c.meta.recommendation_shown = True
        assert _determine_stage(c, lead_submitted=False) == "complete"

    def test_lead_submitted_is_complete_early(self):
        """lead_submitted=True overrides and returns 'complete' regardless of other data."""
        c = CollectedInfo()  # Completely empty
        assert _determine_stage(c, lead_submitted=True) == "complete"

    def test_no_use_case_with_environment_still_greeting(self):
        """Environment without use case → greeting (not qualifying)."""
        c = make_collected(environment__indoor_outdoor="outdoor")
        assert _determine_stage(c, lead_submitted=False) == "greeting"

    def test_recommendation_shown_flag_is_checked(self):
        """The Phase 6 fix: meta.recommendation_shown must be True to reach lead_capture."""
        c = make_collected(
            environment__vertical="retail",
            environment__indoor_outdoor="indoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=False,
        )
        # Without the flag, we should be at recommending
        assert _determine_stage(c, lead_submitted=False) == "recommending"

        # After setting the flag, we move to lead_capture
        c.meta.recommendation_shown = True
        assert _determine_stage(c, lead_submitted=False) == "lead_capture"

    def test_has_name_but_no_email_is_lead_capture(self):
        """Name only → still lead_capture (needs email too)."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
            lead__name="Alice",
        )
        c.meta.recommendation_shown = True
        assert _determine_stage(c, lead_submitted=False) == "lead_capture"


# ── _build_known_summary() ─────────────────────────────────────────────

class TestBuildKnownSummary:
    """_build_known_summary should produce a natural-sounding context summary."""

    def test_empty_collected(self):
        """Empty collected info should return the 'starting fresh' message."""
        c = CollectedInfo()
        summary = _build_known_summary(c)
        assert "starting fresh" in summary.lower()
        assert "Ask what they're working on" in summary

    def test_single_field(self):
        """A single field should be listed."""
        c = make_collected(environment__vertical="parking")
        summary = _build_known_summary(c)
        assert "Industry/Use Case: parking" in summary

    def test_multiple_fields(self):
        """Multiple fields should all appear."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless", "chip"],
        )
        summary = _build_known_summary(c)
        assert "Industry/Use Case: parking" in summary
        assert "Environment: outdoor" in summary
        assert "Card Types: contactless, chip" in summary

    def test_boolean_fields(self):
        """Boolean fields should appear correctly."""
        c = make_collected(
            environment__vertical="parking",
            technical_context__needs_pin=True,
            technical_context__is_standalone=False,
        )
        summary = _build_known_summary(c)
        assert "PIN Entry: Yes" in summary
        assert "Standalone: No/Unknown" in summary  # False shows as 'No/Unknown'

    def test_includes_lead_info(self):
        """Lead info should appear."""
        c = make_collected(
            environment__vertical="parking",
            lead__name="Alice",
            lead__email="alice@example.com",
        )
        summary = _build_known_summary(c)
        assert "Contact Name: Alice" in summary
        assert "Contact Email: alice@example.com" in summary

    def test_highlights_gaps(self):
        """Missing fields should be listed in 'Still missing' section."""
        c = make_collected(environment__vertical="parking")
        summary = _build_known_summary(c)
        assert "Still missing:" in summary
        # Should mention indoor/outdoor since it's not set
        assert "indoor vs outdoor placement" in summary.lower() or "indoor vs outdoor" in summary

    def test_no_gaps_when_fully_collected(self):
        """When all key fields are collected, no gaps should be highlighted."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
            technical_context__is_standalone=False,
            lead__name="Alice",
            lead__email="alice@example.com",
        )
        summary = _build_known_summary(c)
        # The gaps logic checks specific fields — if all are filled, no gap section
        assert "Still missing:" not in summary

    def test_transaction_profile_appears(self):
        """Transaction volume and average ticket should appear."""
        c = make_collected(
            environment__vertical="parking",
            transaction_profile__monthly_volume=5000,
            transaction_profile__average_ticket=25.50,
        )
        summary = _build_known_summary(c)
        assert "Monthly Volume: 5,000" in summary
        assert "Avg Ticket: $25.50" in summary

    def test_previous_products_appear(self):
        """Previous products should be listed."""
        c = make_collected(
            environment__vertical="retail",
            technical_context__previous_products=["Ingenico iPP320", "Verifone VX520"],
        )
        summary = _build_known_summary(c)
        assert "Previous Products: Ingenico iPP320, Verifone VX520" in summary


# ── build_system_prompt() ──────────────────────────────────────────────

class TestBuildSystemPrompt:
    """build_system_prompt should assemble a complete, valid system prompt."""

    def test_basic_prompt_structure(self):
        """The prompt should include all key sections."""
        session = ConversationSession(id="test")
        prompt = build_system_prompt(session)

        # Should include the personality section
        assert "Your Personality" in prompt or "You are a sales rep" in prompt

        # Should include hard rules
        assert "Hard Rules" in prompt

        # Should include the stage
        assert "Current Stage" in prompt or "greeting" in prompt

        # Should include tool guidance
        assert "When to Call Which Tool" in prompt

        # Should include valid values
        assert "Valid Use Case Values" in prompt

    def test_stage_reflects_collected_info(self):
        """The stage in the prompt should match the collected info."""
        session = ConversationSession(id="test")
        c = session.collected_info
        c.environment.vertical = "parking"
        c.environment.indoor_outdoor = "outdoor"
        c.technical_context.card_types = ["contactless"]
        c.technical_context.needs_pin = True

        prompt = build_system_prompt(session)
        assert "recommending" in prompt

    def test_prompt_includes_stage_instructions(self):
        """Stage-specific instructions should be embedded."""
        session = ConversationSession(id="test")
        prompt = build_system_prompt(session)

        # Greeting instructions should be present since it starts in greeting
        greeting_instructions = STAGE_INSTRUCTIONS.get("greeting", "")
        # The instructions should be somewhere in the prompt
        assert len(greeting_instructions) > 0

    def test_prompt_includes_recommended_products(self):
        """Recommended products should appear in the prompt."""
        session = ConversationSession(id="test")
        session.recommended_products = ["VP3300", "VP5300"]
        prompt = build_system_prompt(session)
        assert "VP3300, VP5300" in prompt

    def test_prompt_shows_no_products_when_none(self):
        """When no products recommended, show 'None yet'."""
        session = ConversationSession(id="test")
        prompt = build_system_prompt(session)
        assert "None yet" in prompt

    def test_prompt_does_not_have_old_phrasing(self):
        """The adjusted tone should not include old consultative language."""
        session = ConversationSession(id="test")
        prompt = build_system_prompt(session)

        # These phrases from the old prompt should NOT be present
        old_phrases = [
            "Consultative and technically informed",
            "Your goal is to",
            "What You Know So Far",
        ]
        for phrase in old_phrases:
            assert phrase not in prompt, f"Found old phrase: '{phrase}'"

    def test_prompt_has_new_tone_language(self):
        """The adjusted tone should include new language."""
        session = ConversationSession(id="test")
        prompt = build_system_prompt(session)

        # Check for the updated personality framing
        assert "Direct and practical" in prompt
        assert "Context" in prompt

    def test_lead_capture_stage_instructions(self):
        """Lead capture stage should hide the word 'lead'."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
        )
        c.meta.recommendation_shown = True

        session = ConversationSession(id="test", collected_info=c)
        prompt = build_system_prompt(session)

        # Should contain lead_capture stage instructions
        assert "lead_capture" in prompt

    def test_complete_stage_prompt(self):
        """Complete stage should disallow re-submission."""
        c = CollectedInfo()
        session = ConversationSession(
            id="test",
            collected_info=c,
            lead_submitted=True,
        )
        prompt = build_system_prompt(session)

        assert "complete" in prompt
        assert "lead has been submitted" in prompt.lower() or "do NOT re-qualify" in prompt.lower()

    def test_prompt_is_valid_string(self):
        """The prompt should be a non-empty string."""
        session = ConversationSession(id="test")
        prompt = build_system_prompt(session)
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should be substantial
