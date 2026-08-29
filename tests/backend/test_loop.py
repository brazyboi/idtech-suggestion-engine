"""
Tests for backend.agent.loop.

Covers:
- _build_recommendation() — product recommendation bundle construction
- _dispatch_tool() — tool routing and error handling
- _has_only_faq_intent(), _detect_faq_topic() — helper functions
- process_message() — the main agentic loop (mocked OpenAI)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from backend.agent.loop import (
    _build_recommendation,
    _dispatch_tool,
    _has_only_faq_intent,
    _detect_faq_topic,
    TOOL_MAP,
)
from backend.engine.state_machine import CollectedInfo, ConversationSession, ConversationState
from backend.engine.solution_schemas import RecommendationBundle, HardwareRecommendation
from backend.llm.contracts import ChatResponse


# ── _build_recommendation() ─────────────────────────────────────────────

class TestBuildRecommendation:
    """_build_recommendation should construct RecommendationBundle from product data."""

    def test_empty_products_returns_none(self):
        """Empty product list should return None."""
        result = _build_recommendation([])
        assert result is None

    def test_single_product(self, sample_products_fixture):
        """Single product should produce a valid bundle."""
        products = sample_products_fixture[:1]
        result = _build_recommendation(products)
        assert result is not None
        assert isinstance(result, RecommendationBundle)
        assert result.hardware_name == "VP3300"
        assert len(result.hardware_items) == 1
        assert result.hardware_items[0].name == "VP3300"

    def test_multiple_products(self, sample_products_fixture):
        """Multiple products should produce multiple hardware_items."""
        result = _build_recommendation(sample_products_fixture)
        assert result is not None
        assert len(result.hardware_items) == 2

    def test_explanation_includes_evidence(self, sample_products_fixture):
        """Explanation should reference specs from the top product."""
        result = _build_recommendation(sample_products_fixture)
        assert result is not None
        assert "USB" in result.explanation or "Power" in result.explanation

    def test_highlights_copied(self, sample_products_fixture):
        """Highlights from the product data should be preserved."""
        result = _build_recommendation(sample_products_fixture)
        assert result is not None
        assert len(result.highlights) > 0

    def test_software_included(self, sample_products_fixture):
        """Compatible software should appear in the bundle."""
        result = _build_recommendation(sample_products_fixture)
        assert result is not None
        assert len(result.software) > 0
        assert result.software[0].name == "IDTECH IDPar"

    def test_caps_at_three_items(self, sample_products_fixture):
        """Should not exceed 3 hardware items."""
        many_products = sample_products_fixture * 3  # 6 items
        result = _build_recommendation(many_products)
        assert result is not None
        assert len(result.hardware_items) <= 3


# ── _dispatch_tool() ───────────────────────────────────────────────────

class TestDispatchTool:
    """_dispatch_tool should route tool calls to the correct handler."""

    def test_unknown_tool_returns_error(self):
        """Unknown tool name should return an error JSON."""
        session = ConversationSession(id="test")
        result = _dispatch_tool("nonexistent_tool", {}, session)
        parsed = json.loads(result)
        assert "error" in parsed

    def test_capture_lead_info_routes_correctly(self):
        """capture_lead_info tool should route correctly with session injection."""
        session = ConversationSession(id="test")
        result = _dispatch_tool("capture_lead_info", {"name": "Alice"}, session)
        parsed = json.loads(result)
        assert parsed["status"] == "captured"
        assert session.collected_info.lead.name == "Alice"

    def test_capture_lead_info_no_name(self):
        """capture_lead_info with no info should return no_new_info."""
        session = ConversationSession(id="test")
        result = _dispatch_tool("capture_lead_info", {}, session)
        parsed = json.loads(result)
        assert parsed["status"] == "no_new_info"


# ── _has_only_faq_intent() ─────────────────────────────────────────────

class TestHasOnlyFaqIntent:
    """_has_only_faq_intent should detect simple question-only messages."""

    def test_short_question(self):
        """A short question should return True."""
        assert _has_only_faq_intent("How much does it cost?") is True

    def test_long_message(self):
        """A long message should return False."""
        msg = "We're a parking lot with about 5000 transactions per month. We need outdoor readers and we accept contactless and chip. Also how much does it cost?"
        assert _has_only_faq_intent(msg) is False

    def test_multiple_questions(self):
        """More than 2 question marks should return False."""
        msg = "How much? When does it ship? What about warranty? And returns?"
        assert _has_only_faq_intent(msg) is False

    def test_no_question_mark(self):
        """A message without a question mark should return True (short enough)."""
        assert _has_only_faq_intent("pricing") is True

    def test_exactly_two_questions(self):
        """Exactly 2 question marks should return True."""
        assert _has_only_faq_intent("How much? When does it ship?") is True

    def test_named_product_is_not_pure_faq(self):
        """A short question naming a specific product is a spec question,
        not a FAQ — it must reach the agent loop so get_product_details can
        answer with real specs (regression: 'does the VP6300 support WiFi
        and Cellular?' was previously answered with generic support-hours
        boilerplate instead)."""
        assert _has_only_faq_intent("Does the VP6300 support WiFi and Cellular?") is False
        assert _has_only_faq_intent("Tell me about the AP3880P") is False
        assert _has_only_faq_intent("What about the Kiosk IV?") is False

    def test_named_product_with_stray_space_is_not_pure_faq(self):
        """A space between the model prefix and its digits ('vp 6300') must
        still be recognized as naming a product — regression: this exact
        gap let 'does the vp 6300 support wifi?' fall through to the FAQ
        shortcut live, one space away from the case above."""
        assert _has_only_faq_intent("does the vp 6300 support wifi?") is False
        assert _has_only_faq_intent("what about the ap 3880p") is False


# ── _detect_faq_topic() ────────────────────────────────────────────────

class TestDetectFaqTopic:
    """_detect_faq_topic should detect which FAQ topic is being asked about."""

    def test_pricing_keywords(self):
        assert _detect_faq_topic("how much does it cost") == "pricing"

    def test_shipping_keywords(self):
        assert _detect_faq_topic("when does it ship") == "shipping"

    def test_warranty_keywords(self):
        assert _detect_faq_topic("what's the warranty") == "warranty"

    def test_returns_keywords(self):
        assert _detect_faq_topic("can I return it") == "returns"

    def test_compatibility_keywords(self):
        assert _detect_faq_topic("is it compatible with") == "compatibility"

    def test_security_keywords(self):
        assert _detect_faq_topic("what about PCI security") == "security"

    def test_support_keywords(self):
        assert _detect_faq_topic("I need support") == "support"

    def test_support_as_verb_is_compatibility_not_support_topic(self):
        """'does it support <spec>' asks about capability, not customer
        service — must not be captured by the bare 'support' keyword
        (regression, see test_named_product_is_not_pure_faq above)."""
        assert _detect_faq_topic("does it support WiFi and Cellular") == "compatibility"
        assert _detect_faq_topic("can it support NFC") == "compatibility"

    def test_plural_forms_of_keywords_still_match(self):
        """Keywords are stored singular but customers write plurals. The
        word-boundary matching added to stop 'ach' matching 'reach' also
        silently broke these — each fell through to 'general' until the
        matcher allowed a plural suffix. Every existing test used singular
        forms, so the whole suite stayed green through the regression."""
        assert _detect_faq_topic("what are your rates?") == "pricing"
        assert _detect_faq_topic("do you have returns") == "returns"
        assert _detect_faq_topic("what integrations do you have") == "compatibility"

    def test_ach_does_not_match_words_merely_containing_it(self):
        """The false positive that motivated word-boundary matching:
        merchant_services' 'ach' keyword must not fire on reach/each/coach."""
        assert _detect_faq_topic("how do I reach you") == "support"
        assert _detect_faq_topic("each of these devices") == "general"

    def test_unknown_falls_back_to_general(self):
        assert _detect_faq_topic("tell me about the company") == "general"

    def test_case_insensitive(self):
        assert _detect_faq_topic("HOW MUCH") == "pricing"

    # ── Package A handoff topics: PAE / RDM / RKI / merchant services ──

    def test_payment_integration_keywords(self):
        assert _detect_faq_topic("what is PAE") == "payment_integration"
        assert _detect_faq_topic("tell me about your payment application engine") == "payment_integration"
        assert _detect_faq_topic("do you have EMV Level 3 certification") == "payment_integration"

    def test_device_management_keywords(self):
        assert _detect_faq_topic("what is RDM") == "device_management"
        assert _detect_faq_topic("can you do remote device management") == "device_management"
        assert _detect_faq_topic("how do firmware updates work") == "device_management"

    def test_key_injection_keywords(self):
        assert _detect_faq_topic("what is RKI") == "key_injection"
        assert _detect_faq_topic("tell me about key injection") == "key_injection"
        assert _detect_faq_topic("how does remote key provisioning work") == "key_injection"

    def test_merchant_services_keywords(self):
        assert _detect_faq_topic("tell me about merchant services") == "merchant_services"
        assert _detect_faq_topic("do you support ACH?") == "merchant_services"
        assert _detect_faq_topic("what about P2PE") == "merchant_services"
        assert _detect_faq_topic("what's involved in merchant onboarding") == "merchant_services"

    def test_merchant_services_ach_does_not_collide_with_support(self):
        """'ach' is a substring of common English words like 'reach' — a
        plain substring match would misroute ordinary support questions to
        merchant_services. Word-boundary matching must prevent that."""
        assert _detect_faq_topic("how can I reach support") == "support"
        assert _detect_faq_topic("I need to reach someone") == "support"

    def test_new_topics_do_not_collide_with_existing_eight(self):
        """None of the 4 new topics should shadow the 8 pre-existing ones."""
        assert _detect_faq_topic("how much does it cost") == "pricing"
        assert _detect_faq_topic("when does it ship") == "shipping"
        assert _detect_faq_topic("what's the warranty") == "warranty"
        assert _detect_faq_topic("can I return it") == "returns"
        assert _detect_faq_topic("is it compatible with my POS") == "compatibility"
        assert _detect_faq_topic("what about PCI compliance") == "security"
        assert _detect_faq_topic("I need support") == "support"


# ── process_message() — Chitchat path ──────────────────────────────────

class TestProcessMessageChitchat:
    """process_message should handle the chitchat early-return path with context-aware responses."""

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    def test_chitchat_empty_session(self, mock_extract: MagicMock, mock_classify: MagicMock):
        """With no context, chitchat should ask about their use case."""
        mock_classify.return_value = ("chitchat", 1.0, {})
        mock_extract.return_value = {}

        session = ConversationSession(id="test")
        response = _run_process_message("tell me a joke", session)

        assert response.type == "clarification"
        assert "payment" in response.text.lower() or "hardware" in response.text.lower()
        assert len(session.history) == 2
        assert session.turn_count == 1

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    def test_chitchat_with_history(self, mock_extract: MagicMock, mock_classify: MagicMock):
        """With history but no vertical, chitchat should mention ID TECH hardware."""
        mock_classify.return_value = ("chitchat", 1.0, {})
        mock_extract.return_value = {}

        session = ConversationSession(id="test")
        session.history.append({"role": "user", "content": "hello"})
        session.history.append({"role": "assistant", "content": "What industry?"})
        response = _run_process_message("what's the weather", session)

        assert response.type == "clarification"
        assert "ID TECH" in response.text

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    def test_chitchat_with_vertical(self, mock_extract: MagicMock, mock_classify: MagicMock):
        """With a vertical known, chitchat should focus on that vertical."""
        mock_classify.return_value = ("chitchat", 1.0, {})
        mock_extract.return_value = {}

        session = ConversationSession(id="test")
        session.collected_info.environment.vertical = "parking"
        response = _run_process_message("tell me a joke", session)

        assert response.type == "clarification"
        assert "parking" in response.text.lower()
        assert "hardware" in response.text.lower()


# ── process_message() — Escalate path ──────────────────────────────────

class TestProcessMessageEscalate:
    """process_message should handle the escalate early-return path."""

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    @patch("backend.agent.loop._escalate_to_sales")
    def test_escalate_returns_handoff(self, mock_escalate: MagicMock, mock_extract: MagicMock, mock_classify: MagicMock):
        """Escalate should return a handoff response."""
        mock_classify.return_value = ("escalate", 1.0, {})
        mock_extract.return_value = {}
        mock_escalate.return_value = {
            "status": "escalated",
            "lead_id": 1,
            "message": "A senior sales rep will reach out.",
        }

        session = ConversationSession(id="test")
        response = _run_process_message("I need to talk to a manager", session)

        assert response.type == "clarification"
        assert "sales" in response.text.lower() or "rep" in response.text.lower()
        assert response.next_state == ConversationState.HANDOFF
        assert "offer_booking" in (response.ui_actions or [])


# ── process_message() — FAQ early path ─────────────────────────────────

class TestProcessMessageFaq:
    """process_message should handle the FAQ short-circuit path."""

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    def test_faq_short_circuit(self, mock_extract: MagicMock, mock_classify: MagicMock):
        """A simple FAQ should skip the full agent loop."""
        mock_classify.return_value = ("faq", 1.0, {})
        mock_extract.return_value = {}

        session = ConversationSession(id="test")
        response = _run_process_message("how much does it cost", session)

        assert response.type == "clarification"
        assert len(session.history) == 2
        assert session.turn_count == 1


# ── process_message() — Full loop with tool calls ──────────────────────

class TestProcessMessageFullLoop:
    """process_message should handle the full agent loop with mocked OpenAI."""

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    @patch("backend.agent.loop.OpenAI")
    def test_greeting_with_tool_call(
        self, mock_openai: MagicMock, mock_extract: MagicMock, mock_classify: MagicMock
    ):
        """A greeting should go through the loop and return a response."""
        mock_classify.return_value = ("greeting", 1.0, {})
        mock_extract.return_value = {}

        # Mock the OpenAI response to return no tool calls (simple text response)
        mock_instance = mock_openai.return_value
        mock_choice = MagicMock()
        mock_choice.message.content = "Hi! How can I help you with ID TECH payment hardware today?"
        mock_choice.message.tool_calls = None
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_instance.chat.completions.create.return_value = mock_response

        session = ConversationSession(id="test")
        response = _run_process_message("hello", session)

        assert response.type == "clarification"
        assert len(session.history) == 2
        assert session.turn_count == 1

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    @patch("backend.agent.loop.OpenAI")
    @patch.dict("backend.agent.loop.TOOL_MAP", {"search_products": MagicMock()}, clear=False)
    def test_product_search_with_tool(
        self, mock_openai: MagicMock,
        mock_extract: MagicMock, mock_classify: MagicMock
    ):
        """A product search should trigger the search_products tool and set recommendation_shown."""
        mock_classify.return_value = ("product_search", 1.0, {})
        mock_extract.return_value = {}

        # Mock search_products in TOOL_MAP to return VP3300
        from backend.agent.loop import TOOL_MAP
        mock_search = TOOL_MAP["search_products"]
        mock_search.return_value = {
            "products": [
                {
                    "model_name": "VP3300",
                    "compatible_software": ["IDTECH IDPar"],
                    "highlights": ["Power: USB"],
                    "key_specs": {"input_power": "USB", "interface": "USB"},
                }
            ],
            "count": 1,
            "constraints_used": {"use_case": "retail"},
        }

        # Round 1: LLM returns tool call to search_products
        tool_call_1 = MagicMock()
        tool_call_1.id = "call_1"
        tool_call_1.function.name = "search_products"
        tool_call_1.function.arguments = '{"use_case": "retail"}'

        choice_1 = MagicMock()
        choice_1.message.content = None
        choice_1.message.tool_calls = [tool_call_1]
        choice_1.finish_reason = "tool_calls"

        # Round 2: LLM returns final response
        choice_2 = MagicMock()
        choice_2.message.content = "I recommend the VP3300 for your retail store."
        choice_2.message.tool_calls = None
        choice_2.finish_reason = "stop"

        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create.side_effect = [
            MagicMock(choices=[choice_1]),
            MagicMock(choices=[choice_2]),
        ]

        session = ConversationSession(id="test")
        session.collected_info.environment.vertical = "retail"
        response = _run_process_message("what do you have for retail", session)

        # Verify recommendation_shown was set (Phase 6 fix)
        assert session.collected_info.meta.recommendation_shown is True

        # Verify product was added to session
        assert "VP3300" in session.recommended_products

        # Verify response type
        assert response.type == "recommendation"
        assert response.recommendation is not None
        assert response.recommendation.hardware_name == "VP3300"


# ── MAX_TOOL_ROUNDS safety limit ────────────────────────────────────────

class TestMaxToolRoundsFallback:
    """
    Guards the MAX_TOOL_ROUNDS stopping condition: if the model keeps
    requesting tool calls forever (a misbehaving/looping model, or a tool
    whose result never satisfies it), the loop must bail out with a safe
    fallback response instead of looping indefinitely or crashing.
    """

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    @patch("backend.agent.loop.OpenAI")
    @patch.dict("backend.agent.loop.TOOL_MAP", {"search_products": MagicMock()}, clear=False)
    def test_exhausting_tool_rounds_returns_safe_fallback(
        self, mock_openai: MagicMock, mock_extract: MagicMock, mock_classify: MagicMock
    ):
        mock_classify.return_value = ("product_search", 1.0, {})
        mock_extract.return_value = {}

        from backend.agent.loop import TOOL_MAP, MAX_TOOL_ROUNDS
        TOOL_MAP["search_products"].return_value = {"products": [], "count": 0, "constraints_used": {}}

        # Every round, the model asks for another tool call and never stops.
        tool_call = MagicMock()
        tool_call.id = "call_n"
        tool_call.function.name = "search_products"
        tool_call.function.arguments = "{}"

        looping_choice = MagicMock()
        looping_choice.message.content = None
        looping_choice.message.tool_calls = [tool_call]
        looping_choice.finish_reason = "tool_calls"

        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create.return_value = MagicMock(choices=[looping_choice])

        session = ConversationSession(id="test")
        response = _run_process_message("find me something", session)

        # Bailed out after exactly MAX_TOOL_ROUNDS calls to the LLM, not more.
        assert mock_instance.chat.completions.create.call_count == MAX_TOOL_ROUNDS
        assert response.type == "clarification"
        assert "trouble" in response.text.lower() or "connect" in response.text.lower()
        # The conversation history and turn count must still advance normally
        # so the session isn't left in an inconsistent state.
        assert session.turn_count == 1
        assert session.history[-1]["role"] == "assistant"


class TestOpenAiCallFailureFallback:
    """
    A raw OpenAI SDK error (timeout, rate limit, connection error, etc.)
    during the chat completion call must degrade to the same safe
    fallback response as MAX_TOOL_ROUNDS exhaustion — not propagate up
    as an unhandled exception that the router turns into a bare 500.
    """

    @patch("backend.agent.loop.classify_intent")
    @patch("backend.agent.loop.extract_slots")
    @patch("backend.agent.loop.OpenAI")
    def test_openai_error_returns_safe_fallback_without_raising(
        self, mock_openai: MagicMock, mock_extract: MagicMock, mock_classify: MagicMock
    ):
        from openai import APITimeoutError

        mock_classify.return_value = ("greeting", 1.0, {})
        mock_extract.return_value = {}

        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())

        session = ConversationSession(id="test")
        response = _run_process_message("hello", session)

        assert response.type == "clarification"
        assert "trouble" in response.text.lower() or "connect" in response.text.lower()
        # Only tried once per round — no unbounded retry loop inside process_message
        # (the SDK's own internal retries are separate and already exhausted
        # by the time the exception reaches this code).
        assert mock_instance.chat.completions.create.call_count == 1
        assert session.turn_count == 1


# ── Helper ──────────────────────────────────────────────────────────────

def _run_process_message(message: str, session: ConversationSession) -> ChatResponse:
    """
    Run process_message from the agent.loop module.

    We import here to avoid circular issues with the mock patches.
    """
    from backend.agent.loop import process_message
    return process_message(message, session)


# ── Fixture ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_products_fixture():
    """Sample product data for _build_recommendation tests."""
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
