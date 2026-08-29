"""
Tests for backend.agent.tools.answer_faq.

These tests read from the live faq.json knowledge file, so they validate
the actual content the agent will present to customers.
"""

from __future__ import annotations

import pytest

from backend.agent.tools.answer_faq import answer_faq


class TestAnswerFaq:
    """answer_faq should return verbatim answers from the knowledge file."""

    def test_pricing_topic_exists(self):
        """Pricing FAQ should return a non-empty answer about pricing."""
        result = answer_faq("pricing")
        assert "error" not in result
        assert len(result["answer"]) > 20
        assert "pricing" in result["answer"].lower() or "quote" in result["answer"].lower()

    def test_pricing_answer_does_not_contain_specific_prices(self):
        """Pricing FAQ should never state a specific price."""
        result = answer_faq("pricing")
        assert "$" not in result["answer"]  # No dollar amounts

    def test_shipping_topic(self):
        """Shipping FAQ should mention shipping."""
        result = answer_faq("shipping")
        assert "error" not in result
        assert "shipping" in result["answer"].lower() or "delivery" in result["answer"].lower()

    def test_warranty_topic(self):
        """Warranty FAQ should mention warranty."""
        result = answer_faq("warranty")
        assert "error" not in result
        assert "warranty" in result["answer"].lower()

    def test_returns_topic(self):
        """Returns FAQ should mention returns."""
        result = answer_faq("returns")
        assert "error" not in result
        assert "return" in result["answer"].lower()

    def test_compatibility_topic(self):
        """Compatibility FAQ should mention compatibility."""
        result = answer_faq("compatibility")
        assert "error" not in result
        assert "compatible" in result["answer"].lower() or "compatibility" in result["answer"].lower()

    def test_security_topic(self):
        """Security FAQ should mention security."""
        result = answer_faq("security")
        assert "error" not in result
        assert "security" in result["answer"].lower() or "PCI" in result["answer"]

    def test_support_topic(self):
        """Support FAQ should mention support."""
        result = answer_faq("support")
        assert "error" not in result
        assert "support" in result["answer"].lower()

    def test_general_topic(self):
        """General FAQ should return a non-empty answer."""
        result = answer_faq("general")
        assert "error" not in result
        assert len(result["answer"]) > 10

    def test_case_insensitive_topic(self):
        """Topic matching should be case-insensitive."""
        result_upper = answer_faq("PRICING")
        result_lower = answer_faq("pricing")
        assert result_upper["answer"] == result_lower["answer"]

    def test_partial_match(self):
        """Partial topic matching should work (e.g. 'price' matches 'pricing')."""
        result = answer_faq("price")
        assert "error" not in result
        assert len(result["answer"]) > 10

    def test_unknown_topic_falls_back(self):
        """Unknown topics should fall back to general."""
        result = answer_faq("nonexistent_topic_xyz")
        assert "error" not in result
        assert len(result["answer"]) > 10

    def test_response_has_instruction_field(self):
        """Response should include the '_instruction' telling the agent to present verbatim."""
        result = answer_faq("pricing")
        assert "_instruction" in result
        assert "verbatim" in result["_instruction"].lower()

    def test_response_has_topic_field(self):
        """Response should echo back the requested topic."""
        result = answer_faq("shipping")
        assert result["topic"] == "shipping"

    def test_all_topics_accessible(self):
        """All standard topics should return valid answers."""
        for topic in ["pricing", "shipping", "warranty", "returns", "compatibility", "security", "support", "general"]:
            result = answer_faq(topic)
            assert "error" not in result, f"Topic '{topic}' returned an error"
            assert len(result["answer"]) > 10, f"Topic '{topic}' has a very short answer"


class TestHandoffTopics:
    """PAE / RDM / RKI / merchant_services should recognize-and-hand-off:
    a short approved description that ends with an explicit handoff offer,
    never a deep Q&A capability."""

    _HANDOFF_TOPICS = ["payment_integration", "device_management", "key_injection", "merchant_services"]

    def test_all_handoff_topics_return_nonempty_answers(self):
        for topic in self._HANDOFF_TOPICS:
            result = answer_faq(topic)
            assert "error" not in result, f"Topic '{topic}' returned an error"
            assert len(result["answer"]) > 20, f"Topic '{topic}' has a very short answer"

    def test_all_handoff_topics_offer_a_handoff(self):
        for topic in self._HANDOFF_TOPICS:
            result = answer_faq(topic)
            answer = result["answer"].lower()
            assert "connect" in answer or "specialist" in answer, (
                f"Topic '{topic}' answer doesn't offer a handoff: {result['answer']!r}"
            )

    def test_payment_integration_topic(self):
        result = answer_faq("payment_integration")
        answer = result["answer"].lower()
        assert "pae" in answer or "payment application engine" in answer

    def test_device_management_topic(self):
        result = answer_faq("device_management")
        answer = result["answer"].lower()
        assert "rdm" in answer or "remote device management" in answer

    def test_key_injection_topic(self):
        result = answer_faq("key_injection")
        answer = result["answer"].lower()
        assert "rki" in answer or "remote key injection" in answer

    def test_merchant_services_topic(self):
        result = answer_faq("merchant_services")
        answer = result["answer"].lower()
        assert "merchant" in answer

    def test_merchant_services_does_not_fabricate_echeck_ach_capability(self):
        """CRITICAL accuracy constraint: ID TECH's approved copy does not
        claim eCheck, ACH, virtual-terminal, invoicing, or payment-link
        capability — those came from an inbound prospect question, not
        ID TECH's own material. The answer must route those asks to a human
        without asserting the capability exists."""
        result = answer_faq("merchant_services")
        answer = result["answer"].lower()
        for term in ("echeck", "e-check", "virtual terminal", "invoicing", "payment link"):
            assert term not in answer, (
                f"merchant_services answer asserts an unapproved capability ({term!r}): {result['answer']!r}"
            )
        # ACH itself is fine to name as something a specialist can confirm,
        # just never asserted as a capability ID TECH's copy claims.
        assert "supports ach" not in answer and "ach support" not in answer
