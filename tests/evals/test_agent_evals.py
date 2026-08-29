"""
Golden-case eval suite for the agentic loop (backend/agent/loop.py).

Unlike tests/backend/, these hit the real OpenAI API through the real agent
loop end to end — no mocked LLM. Unit tests check that the code paths exist;
these check that the *model* behaves: picks the right tool, grounds its
answer in real product data instead of generic boilerplate, and never states
a price. That gap is not hypothetical — the VP6300 case below reproduces a
bug found by manually testing the live app (see ARCHITECTURE.md), where a
spec question was silently answered with unrelated canned FAQ text. A test
like test_named_product_question_uses_real_spec would have caught it
immediately instead of requiring someone to notice a bad reply by hand.

Run with:  RUN_EVALS=1 pytest tests/evals
Requires a real OPENAI_API_KEY (real cost per run — small, but not free).
Skipped automatically otherwise (see conftest.py).
"""

from __future__ import annotations

import re

from backend.agent.loop import process_message
from backend.engine.state_machine import ConversationSession

_PRICE_PATTERN = re.compile(r"\$\s?\d")


def _fresh_session(session_id: str) -> ConversationSession:
    return ConversationSession(id=session_id)


class TestFaqRoutingGroundedInRealData:
    """A question naming a specific product must be answered from that
    product's real data (via get_product_details / search_products), not a
    generic canned FAQ reply that happens to keyword-match."""

    def test_named_product_spec_question_uses_real_spec(self, seeded_catalog):
        session = _fresh_session("eval-vp6300-connectivity")
        resp = process_message("Does the VP6300 support WiFi and Cellular?", session)

        text = resp.text.lower()
        assert "wifi" in text and "cellular" in text, (
            f"Expected the real VP6300 connectivity spec in the answer, got: {resp.text!r}"
        )
        # The bug this guards against: misrouting to the generic "support"
        # FAQ topic (business-hours boilerplate) instead of the real spec.
        assert "business hours" not in text and "24/7" not in text, (
            f"Answer looks like the generic support-hours FAQ, not a real spec answer: {resp.text!r}"
        )

    def test_terse_lowercase_pricing_phrasing_still_deflects(self, seeded_catalog):
        """Short/lowercase/terse phrasing variety — the same guardrail must
        hold regardless of capitalization or verbosity, not just the
        well-formed "How much does it cost?" phrasing."""
        session = _fresh_session("eval-pricing-terse")
        resp = process_message("cost?", session)

        assert not _PRICE_PATTERN.search(resp.text), f"Fabricated a price: {resp.text!r}"

    def test_short_ambiguous_compatibility_phrasing_uses_real_spec(self, seeded_catalog):
        """Was flaky (xfail) under the theory that this was LLM tool-choice
        non-determinism. Root cause was actually deterministic and simpler:
        get_tools_for_intent("faq") never included get_product_details at
        all, so the model had no way to call it regardless of phrasing —
        not a "choice" it was making. Fixed in loop.py by adding
        get_product_details to the tool list whenever the message names a
        known product, independent of classified intent. No longer flaky."""
        session = _fresh_session("eval-vp6300-short-phrasing")
        resp = process_message("does the vp 6300 support wifi?", session)
        session = _fresh_session("eval-vp6300-short-phrasing")
        resp = process_message("does the vp 6300 support wifi?", session)

        text = resp.text.lower()
        assert "wifi" in text, f"Expected the real VP6300 spec in the answer, got: {resp.text!r}"

    def test_unnamed_product_pricing_question_still_deflects(self, seeded_catalog):
        """Pricing questions without a product name go through the FAQ
        short-circuit and must use the approved verbatim deflection."""
        session = _fresh_session("eval-pricing-generic")
        resp = process_message("How much does it cost?", session)

        assert not _PRICE_PATTERN.search(resp.text), f"Fabricated a price: {resp.text!r}"
        assert "specialist" in resp.text.lower() or "quote" in resp.text.lower()


class TestPricingNeverFabricated:
    """Pricing safety must hold even when a product name pulls the message
    out of the FAQ short-circuit and into the full tool-calling agent loop,
    where the guardrail is a system-prompt instruction, not a code path."""

    def test_named_product_pricing_question_never_states_a_price(self, seeded_catalog):
        session = _fresh_session("eval-pricing-named-product")
        resp = process_message("How much does the VP3300 cost?", session)

        assert not _PRICE_PATTERN.search(resp.text), (
            f"Agent loop fabricated a price for a named product: {resp.text!r}"
        )

    def test_pricing_question_phrased_as_qualification_answer_never_states_a_price(self, seeded_catalog):
        """Priority case for the qualification tool-surface gap: a message
        that mixes qualification info (deployment volume) with an implicit
        cost question is exactly the phrasing the classifier is prone to
        route to "qualification" instead of "faq" — and before
        get_tools_for_intent("qualification") included answer_faq, that
        intent had no way to reach the pricing guardrail at all."""
        session = _fresh_session("eval-pricing-qualification-phrasing")
        process_message(
            "We're a parking operator looking at outdoor readers.",
            session,
        )
        resp = process_message(
            "Roughly 500 units across our lots — what would that run us?",
            session,
        )

        assert not _PRICE_PATTERN.search(resp.text), (
            f"Agent loop fabricated a price on a qualification-phrased pricing question: {resp.text!r}"
        )
        assert "specialist" in resp.text.lower() or "quote" in resp.text.lower() or "connect" in resp.text.lower(), (
            f"Expected a deflection/handoff offer, got: {resp.text!r}"
        )


class TestEscalationReachesHandoff:
    def test_explicit_human_request_escalates(self, seeded_catalog):
        session = _fresh_session("eval-escalate")
        resp = process_message("I want to talk to a real person, not a bot.", session)

        assert resp.next_state == "handoff", (
            f"Expected escalation to reach handoff state, got next_state={resp.next_state!r}"
        )


class TestChitchatDoesNotDerailQualification:
    def test_off_topic_message_redirects_to_hardware(self, seeded_catalog):
        session = _fresh_session("eval-chitchat")
        resp = process_message("Tell me a joke about cats.", session)

        text = resp.text.lower()
        assert "payment" in text or "hardware" in text or "id tech" in text, (
            f"Expected a redirect back to payment hardware, got: {resp.text!r}"
        )


class TestRecommendationMatchesStatedConstraints:
    """A qualification flow with a clear constraint (outdoor + PIN + RS232)
    must recommend hardware that actually satisfies it — not just any
    in-catalog product."""

    def test_outdoor_pin_rs232_recommends_matching_hardware(self, seeded_catalog):
        session = _fresh_session("eval-recommend-outdoor")
        process_message(
            "I run an outdoor parking garage and need PIN entry and RS232 for the host connection.",
            session,
        )
        resp = process_message(
            "Contactless and chip cards, standalone kiosk, yes we need a display.",
            session,
        )

        assert resp.recommendation is not None, (
            f"Expected a recommendation after full qualification, got type={resp.type!r} text={resp.text!r}"
        )
        recommended_names = {item.name for item in resp.recommendation.hardware_items}
        # VP3300 is indoor/USB-only in the seeded catalog — recommending it
        # for an outdoor/RS232 requirement would be a real matching failure.
        assert "VP3300" not in recommended_names, (
            f"Recommended indoor USB-only VP3300 for an outdoor RS232 requirement: {recommended_names}"
        )
        assert "VP7200" in recommended_names, (
            f"Expected the outdoor RS232 product VP7200 in the recommendation, got: {recommended_names}"
        )
