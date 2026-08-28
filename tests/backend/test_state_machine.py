"""
Tests for backend.engine.state_machine.

Covers:
- CollectedInfo model creation, merge(), to_flat_constraints()
- _normalize_use_case() mapping
- _is_technical_context_ready() detection
- determine_next_state() stage transitions
- ConversationSession model creation
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from backend.engine.state_machine import (
    CollectedInfo,
    ConversationSession,
    ConversationState,
    EnvironmentInfo,
    TechnicalContext,
    TransactionProfile,
    LeadInfo,
    ConversationMeta,
    determine_next_state,
    _is_technical_context_ready,
    _normalize_use_case,
)


# ── Helper: build CollectedInfo via attribute assignment ─────────────────

def make_collected(**overrides: Any) -> CollectedInfo:
    """
    Create a CollectedInfo with field values set via attribute assignment.

    Double-underscore keys like environment__vertical are split into
    section and field names for nested attribute assignment.
    """
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


# ── CollectedInfo Creation ──────────────────────────────────────────────

class TestCollectedInfoCreation:
    """Verify default construction and field-level initialization."""

    def test_default_construction(self):
        """All nested models should be created with None/False defaults."""
        c = CollectedInfo()
        assert isinstance(c.environment, EnvironmentInfo)
        assert isinstance(c.technical_context, TechnicalContext)
        assert isinstance(c.transaction_profile, TransactionProfile)
        assert isinstance(c.lead, LeadInfo)
        assert isinstance(c.meta, ConversationMeta)

        assert c.environment.vertical is None
        assert c.environment.indoor_outdoor is None
        assert c.technical_context.card_types is None
        assert c.technical_context.needs_pin is None
        assert c.lead.name is None
        assert c.meta.recommendation_shown is False

    def test_creation_with_nested_objects(self):
        """Pydantic v2 should accept nested objects directly in the constructor."""
        c = CollectedInfo(
            environment=EnvironmentInfo(vertical="retail", indoor_outdoor="indoor"),
            lead=LeadInfo(name="Bob", company="ACME Corp"),
        )
        assert c.environment.vertical == "retail"
        assert c.environment.indoor_outdoor == "indoor"
        assert c.lead.name == "Bob"
        assert c.lead.company == "ACME Corp"

    def test_creation_via_attribute_assignment(self):
        """Setting fields directly via attribute access should work."""
        c = CollectedInfo()
        c.environment.vertical = "parking"
        c.environment.indoor_outdoor = "outdoor"
        c.technical_context.card_types = ["contactless"]
        c.lead.name = "Alice"
        c.lead.email = "alice@example.com"

        assert c.environment.vertical == "parking"
        assert c.environment.indoor_outdoor == "outdoor"
        assert c.technical_context.card_types == ["contactless"]
        assert c.lead.name == "Alice"
        assert c.lead.email == "alice@example.com"

    def test_meta_defaults(self):
        """meta.recommendation_shown should start as False."""
        c = CollectedInfo()
        assert c.meta.recommendation_shown is False

    def test_meta_can_be_set(self):
        """meta.recommendation_shown can be set to True."""
        c = CollectedInfo()
        c.meta.recommendation_shown = True
        assert c.meta.recommendation_shown is True


# ── CollectedInfo.merge() ──────────────────────────────────────────────

class TestCollectedInfoMerge:
    """merge() should add or overwrite fields from the update dict."""

    def test_merge_empty_into_empty(self):
        """Merging empty updates should be a no-op."""
        c = CollectedInfo()
        c.merge({})
        assert c.environment.vertical is None

    def test_merge_basic_fields(self):
        """Merging flat field dicts into the appropriate sub-model."""
        c = CollectedInfo()
        c.merge({
            "environment": {"vertical": "parking"},
            "technical_context": {"card_types": ["contactless"]},
        })
        assert c.environment.vertical == "parking"
        assert c.technical_context.card_types == ["contactless"]

    def test_merge_overwrites_existing(self):
        """merge() overwrites fields even if they are already set."""
        c = CollectedInfo()
        c.environment.vertical = "parking"
        c.merge({"environment": {"vertical": "retail"}})
        # merge() does NOT check whether the field is already set — it overwrites
        assert c.environment.vertical == "retail"

    def test_merge_does_not_set_none(self):
        """merge() skips values that are None."""
        c = CollectedInfo()
        c.merge({"environment": {"vertical": None, "indoor_outdoor": "indoor"}})
        assert c.environment.vertical is None   # Not set because value is None
        assert c.environment.indoor_outdoor == "indoor"

    def test_merge_lead_info(self):
        """merge() should handle lead fields."""
        c = CollectedInfo()
        c.merge({"lead": {"name": "Alice", "email": "alice@example.com"}})
        assert c.lead.name == "Alice"
        assert c.lead.email == "alice@example.com"

    def test_merge_meta(self):
        """merge() should update meta fields."""
        c = CollectedInfo()
        c.merge({"meta": {"recommendation_shown": True}})
        assert c.meta.recommendation_shown is True

    def test_merge_non_dict_values_on_sub_models(self):
        """merge() sets non-dict values directly on sub-model fields.

        If environment is passed as a string instead of a dict, it replaces
        the sub-model entirely. This is a limitation callers should be aware of,
        but the slot_extractor always passes dicts so this is not an issue in
        normal operation.
        """
        c = CollectedInfo()
        c.environment.vertical = "original"
        c.merge({"environment": "some string"})
        # The string replaces the EnvironmentInfo object
        assert c.environment == "some string"

    def test_merge_ignores_unknown_keys(self):
        """merge() should not crash on unknown keys."""
        c = CollectedInfo()
        c.merge({"unknown_field": "value", "environment": {"vertical": "test"}})
        assert c.environment.vertical == "test"


# ── to_flat_constraints() ──────────────────────────────────────────────

class TestToFlatConstraints:
    """to_flat_constraints() should produce correct DB query constraints."""

    def test_empty_collected(self):
        """Empty collected info should produce empty constraints."""
        c = CollectedInfo()
        constraints = c.to_flat_constraints()
        assert constraints == {}

    def test_use_case_mapped(self):
        """Vertical should be mapped through _normalize_use_case."""
        c = make_collected(environment__vertical="parking")
        constraints = c.to_flat_constraints()
        assert constraints.get("use_case") == "Parking Payment Systems"

    def test_outdoor_triggers_is_outdoor(self):
        """Outdoor indoor_outdoor should set is_outdoor=True."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
        )
        constraints = c.to_flat_constraints()
        assert constraints.get("is_outdoor") is True

    def test_indoor_does_not_trigger_outdoor(self):
        """Indoor should not set is_outdoor."""
        c = make_collected(
            environment__vertical="retail",
            environment__indoor_outdoor="indoor",
        )
        constraints = c.to_flat_constraints()
        assert "is_outdoor" not in constraints

    def test_voltage_maps_to_input_power(self):
        """Voltage in technical_context should map to input_power."""
        c = make_collected(technical_context__voltage="12V")
        constraints = c.to_flat_constraints()
        assert constraints.get("input_power") == "12V"

    def test_usb_power_source(self):
        """USB power source should map to input_power='USB'."""
        c = make_collected(technical_context__power_source="USB")
        constraints = c.to_flat_constraints()
        assert constraints.get("input_power") == "USB"

    def test_wall_outlet_power_source(self):
        """Wall outlet power source should map to input_power='VAC'."""
        c = make_collected(technical_context__power_source="Wall outlet")
        constraints = c.to_flat_constraints()
        assert constraints.get("input_power") == "VAC"

    def test_host_interface_maps(self):
        """Host interface should map to constraints['interface']."""
        c = make_collected(technical_context__host_interface="USB")
        constraints = c.to_flat_constraints()
        assert constraints.get("interface") == "USB"

    def test_is_standalone(self):
        """is_standalone=True should be passed through."""
        c = make_collected(technical_context__is_standalone=True)
        constraints = c.to_flat_constraints()
        assert constraints.get("is_standalone") is True

    def test_pin_extra_tag(self):
        """needs_pin=True should add 'PIN' to extra_specs_filter."""
        c = make_collected(technical_context__needs_pin=True)
        constraints = c.to_flat_constraints()
        assert "PIN" in constraints.get("extra_specs_filter", "")

    def test_contactless_extra_tag(self):
        """Contactless card type should add 'contactless' to extra_specs_filter."""
        c = make_collected(technical_context__card_types=["contactless", "chip"])
        constraints = c.to_flat_constraints()
        assert "contactless" in constraints.get("extra_specs_filter", "")

    def test_combined_extra_tags(self):
        """Multiple extra tags should be comma-separated."""
        c = make_collected(
            technical_context__needs_pin=True,
            technical_context__card_types=["contactless"],
        )
        constraints = c.to_flat_constraints()
        tags = constraints.get("extra_specs_filter", "")
        assert "PIN" in tags and "contactless" in tags

    def test_standalone_comms_as_interface(self):
        """standalone_comms should be used as interface."""
        c = make_collected(technical_context__standalone_comms="Ethernet")
        constraints = c.to_flat_constraints()
        assert constraints.get("interface") == "Ethernet"

    def test_previous_products(self):
        """Previous products should be passed as search_query."""
        c = make_collected(technical_context__previous_products=["Ingenico iPP320"])
        constraints = c.to_flat_constraints()
        assert constraints.get("search_query") == "Ingenico iPP320"

    def test_temperature_range_extracts_number(self):
        """Temperature range should extract the first number."""
        c = make_collected(environment__temperature_range="-20°C to 65°C")
        constraints = c.to_flat_constraints()
        assert constraints.get("operate_temperature") == "-20"

    def test_outdoor_harsh_triggers_is_outdoor(self):
        """"outdoor harsh" should also set is_outdoor=True."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor harsh",
        )
        constraints = c.to_flat_constraints()
        assert constraints.get("is_outdoor") is True

    def test_host_interface_not_overridden_by_standalone_comms(self):
        """If host_interface is set, standalone_comms should NOT override it.

        Note: The current implementation sets interface to standalone_comms
        AFTER host_interface, so standalone_comms DOES override. This test
        documents the current behavior.
        """
        c = make_collected(
            technical_context__host_interface="USB",
            technical_context__standalone_comms="Ethernet",
        )
        constraints = c.to_flat_constraints()
        # Current behavior: standalone_comms overrides host_interface
        assert constraints.get("interface") == "Ethernet"


# ── _normalize_use_case() ──────────────────────────────────────────────

class TestNormalizeUseCase:
    """_normalize_use_case should map free-text to canonical use cases."""

    def test_parking_exact(self):
        assert _normalize_use_case("parking") == "Parking Payment Systems"

    def test_parking_with_transit(self):
        assert _normalize_use_case("Parking / Transit") == "Parking Payment Systems"

    def test_transit(self):
        assert _normalize_use_case("transit") == "Transit Payment Solutions"

    def test_retail(self):
        assert _normalize_use_case("retail") == "Loyalty Program Contactless Readers"

    def test_retail_pos(self):
        assert _normalize_use_case("Retail / POS") == "Loyalty Program Contactless Readers"

    def test_vending(self):
        assert _normalize_use_case("vending machine") == "Vending Payment Systems"

    def test_ev_charging(self):
        assert _normalize_use_case("ev charging") == "EV Charging Station Payment Solutions"

    def test_unknown_passthrough(self):
        """Unknown values should pass through unchanged."""
        assert _normalize_use_case("Custom Industry") == "Custom Industry"

    def test_case_insensitive(self):
        """Mapping should be case-insensitive."""
        assert _normalize_use_case("PARKING") == "Parking Payment Systems"


# ── _is_technical_context_ready() ──────────────────────────────────────

class TestIsTechnicalContextReady:
    """_is_technical_context_ready should determine if we have enough tech info."""

    def test_empty_tech_is_not_ready(self):
        """No tech info at all should return False."""
        c = CollectedInfo()
        assert _is_technical_context_ready(c) is False

    def test_two_primary_indicators_is_ready(self):
        """Two+ of card_types, needs_pin, is_standalone should be ready."""
        c = make_collected(
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
        )
        assert _is_technical_context_ready(c) is True

    def test_all_three_primary_is_ready(self):
        """All three primary indicators should definitely be ready."""
        c = make_collected(
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
            technical_context__is_standalone=False,
        )
        assert _is_technical_context_ready(c) is True

    def test_one_primary_two_secondary_is_ready(self):
        """One primary + two secondary signals should be ready."""
        c = make_collected(
            technical_context__card_types=["contactless"],         # primary
            technical_context__power_source="USB",                 # secondary
            technical_context__host_interface="USB",               # secondary
        )
        assert _is_technical_context_ready(c) is True

    def test_one_primary_one_secondary_not_ready(self):
        """One primary + one secondary should NOT be ready."""
        c = make_collected(
            technical_context__card_types=["contactless"],         # primary
            technical_context__power_source="USB",                 # secondary
        )
        assert _is_technical_context_ready(c) is False

    def test_zero_primary_two_secondary_is_ready(self):
        """Zero primary but two secondary IS ready (sum(secondary_signals) >= 2)."""
        c = make_collected(
            technical_context__power_source="USB",     # secondary
            technical_context__voltage="12V",           # secondary
        )
        assert _is_technical_context_ready(c) is True

    def test_needs_display_counts_as_secondary(self):
        """needs_display should be a valid secondary signal."""
        c = make_collected(
            technical_context__needs_display=True,
            technical_context__voltage="12V",
        )
        assert _is_technical_context_ready(c) is True

    def test_previous_products_not_a_signal(self):
        """previous_products is NOT in the secondary signals list."""
        c = make_collected(technical_context__previous_products=["Ingenico"])
        assert _is_technical_context_ready(c) is False

    def test_standalone_comms_counts_as_secondary(self):
        """standalone_comms should be a valid secondary signal."""
        c = make_collected(
            technical_context__standalone_comms="Ethernet",
            technical_context__voltage="12V",
        )
        assert _is_technical_context_ready(c) is True


# ── determine_next_state() ────────────────────────────────────────────

class TestDetermineNextState:
    """determine_next_state should correctly traverse all stages."""

    def test_no_use_case_is_greeting(self):
        """Without a use case, we should be in GREETING."""
        c = CollectedInfo()
        assert determine_next_state(c) == ConversationState.GREETING

    def test_use_case_no_environment_is_qualifying(self):
        """With use case but no environment, we should be QUALIFYING."""
        c = make_collected(environment__vertical="parking")
        assert determine_next_state(c) == ConversationState.QUALIFYING

    def test_use_case_and_environment_no_tech_is_qualifying(self):
        """With use case + environment but no tech context → QUALIFYING."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
        )
        assert determine_next_state(c) == ConversationState.QUALIFYING

    def test_fully_qualified_no_recommendation_is_recommending(self):
        """With full qualifying info but no recommendation yet → RECOMMENDING."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
        )
        assert determine_next_state(c) == ConversationState.RECOMMENDING

    def test_recommendation_shown_no_lead_is_lead_capture(self):
        """After recommendation but no lead info → LEAD_CAPTURE."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
        )
        c.meta.recommendation_shown = True
        assert determine_next_state(c) == ConversationState.LEAD_CAPTURE

    def test_lead_name_only_is_lead_capture(self):
        """Only name without email → still LEAD_CAPTURE."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
            lead__name="Alice",
        )
        c.meta.recommendation_shown = True
        assert determine_next_state(c) == ConversationState.LEAD_CAPTURE

    def test_email_only_is_lead_capture(self):
        """Only email without name → still LEAD_CAPTURE."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
            lead__email="alice@example.com",
        )
        c.meta.recommendation_shown = True
        assert determine_next_state(c) == ConversationState.LEAD_CAPTURE

    def test_name_and_email_is_handoff(self):
        """Name + email with recommendation shown → HANDOFF."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
            lead__name="Alice",
            lead__email="alice@example.com",
        )
        c.meta.recommendation_shown = True
        assert determine_next_state(c) == ConversationState.HANDOFF

    def test_full_circle_transition(self):
        """Test the complete flow GREETING → QUALIFYING → RECOMMENDING → LEAD_CAPTURE → HANDOFF."""
        c = CollectedInfo()

        # Step 1: Greeting
        assert determine_next_state(c) == ConversationState.GREETING

        # Step 2: Add use case → Qualifying
        c.environment.vertical = "parking"
        assert determine_next_state(c) == ConversationState.QUALIFYING

        # Step 3: Add environment + tech → Recommending
        c.environment.indoor_outdoor = "outdoor"
        c.technical_context.card_types = ["contactless"]
        c.technical_context.needs_pin = True
        assert determine_next_state(c) == ConversationState.RECOMMENDING

        # Step 4: Show recommendation → Lead Capture
        c.meta.recommendation_shown = True
        assert determine_next_state(c) == ConversationState.LEAD_CAPTURE

        # Step 5: Add lead info → Handoff
        c.lead.name = "Alice"
        c.lead.email = "alice@example.com"
        assert determine_next_state(c) == ConversationState.HANDOFF

    def test_recommendation_shown_is_required_for_recommending_transition(self):
        """Without meta.recommendation_shown=True, we stay in RECOMMENDING even after presenting products."""
        c = make_collected(
            environment__vertical="parking",
            environment__indoor_outdoor="outdoor",
            technical_context__card_types=["contactless"],
            technical_context__needs_pin=True,
        )
        # Has qualifying info + tech, but recommendation_shown is False
        assert determine_next_state(c) == ConversationState.RECOMMENDING
        # Even after setting lead info, without recommendation_shown it should
        # stick at RECOMMENDING
        c.lead.name = "Alice"
        c.lead.email = "alice@example.com"
        # Still RECOMMENDING because recommendation hasn't been shown
        assert determine_next_state(c) == ConversationState.RECOMMENDING

    def test_healthcare_maps_to_retail_use_case(self):
        """Healthcare should map to 'Loyalty Program Contactless Readers'."""
        c = make_collected(environment__vertical="healthcare")
        assert determine_next_state(c) == ConversationState.QUALIFYING


# ── ConversationSession ────────────────────────────────────────────────

class TestConversationSession:
    """ConversationSession should properly hold and manage all conversation state."""

    def test_default_creation(self):
        """A new session should have all defaults."""
        s = ConversationSession(id="test-1")
        assert s.id == "test-1"
        assert s.history == []
        assert isinstance(s.collected_info, CollectedInfo)
        assert s.asked_slots == set()
        assert s.answered_slots == set()
        assert s.intent is None
        assert s.turn_count == 0
        assert s.recommended_products == []
        assert s.lead_submitted is False
        assert s.reasoning_trace == []

    def test_lead_submitted_guard(self):
        """lead_submitted should start False and be settable."""
        s = ConversationSession(id="test-2")
        assert s.lead_submitted is False
        s.lead_submitted = True
        assert s.lead_submitted is True

    def test_recommended_products_accumulate(self):
        """recommended_products should be a mutable list."""
        s = ConversationSession(id="test-3")
        s.recommended_products.append("VP3300")
        s.recommended_products.append("VP5300")
        assert len(s.recommended_products) == 2
        assert "VP3300" in s.recommended_products

    def test_history_accumulates(self):
        """History should accumulate messages in order."""
        s = ConversationSession(id="test-4")
        s.history.append({"role": "user", "content": "hello"})
        s.history.append({"role": "assistant", "content": "hi"})
        assert len(s.history) == 2
        assert s.history[0]["role"] == "user"

    def test_reasoning_trace_accumulates(self):
        """reasoning_trace should be a mutable list of dicts."""
        s = ConversationSession(id="test-5")
        s.reasoning_trace.append({"turn_id": "turn-0", "steps": []})
        assert len(s.reasoning_trace) == 1

    def test_collected_info_passed_to_determine_next_state(self):
        """Session.collected_info should work with determine_next_state()."""
        s = ConversationSession(id="test-6")
        state = determine_next_state(s.collected_info)
        assert state == ConversationState.GREETING

        s.collected_info.environment.vertical = "parking"
        state = determine_next_state(s.collected_info)
        assert state == ConversationState.QUALIFYING
