"""
Tests for backend.agent.tools.registry — the intent -> tool-surface mapping.

This filtering is what keeps the agent from hallucinating unrelated tool
calls (e.g. offering to submit a lead during a pure FAQ question). It was
untested before this file existed, so a typo in one of the intent_tools
keys could silently give an intent zero (or the wrong) tools with no
test catching it.
"""

from backend.agent.tools.registry import (
    get_all_tools,
    get_tools_for_intent,
    CAPTURE_LEAD_INFO_TOOL,
    SEARCH_PRODUCTS_TOOL,
    SUBMIT_LEAD_TOOL,
    ESCALATE_TO_SALES_TOOL,
    ANSWER_FAQ_TOOL,
    GET_PRODUCT_DETAILS_TOOL,
    GET_SOLUTION_CONTENT_TOOL,
)


def _names(tools):
    return {t["function"]["name"] for t in tools}


class TestGetAllTools:
    def test_returns_seven_unique_tools(self):
        tools = get_all_tools()
        names = _names(tools)
        assert len(tools) == 7
        assert len(names) == 7  # no duplicates

    def test_every_tool_has_a_name_description_and_parameters(self):
        for tool in get_all_tools():
            fn = tool["function"]
            assert tool["type"] == "function"
            assert fn["name"]
            assert fn["description"]
            assert "parameters" in fn


class TestGetToolsForIntent:
    def test_capture_lead_info_is_always_present(self):
        for intent in ("product_search", "faq", "qualification", "lead_capture", "escalate", "greeting", "chitchat"):
            assert CAPTURE_LEAD_INFO_TOOL in get_tools_for_intent(intent)

    def test_faq_intent_offers_answer_faq_and_escalation(self):
        """escalate_to_sales must be offered on faq — the approved pricing
        answer itself offers to connect the customer to a specialist, so the
        model needs a tool to act on "yes, connect me"."""
        names = _names(get_tools_for_intent("faq"))
        assert names == {"capture_lead_info", "answer_faq", "escalate_to_sales"}

    def test_product_search_intent_offers_product_tools(self):
        names = _names(get_tools_for_intent("product_search"))
        assert "search_products" in names
        assert "get_product_details" in names
        assert "get_solution_content" in names
        # Should NOT be able to submit a lead purely from a product search intent
        assert "submit_lead" not in names

    def test_escalate_intent_offers_escalation_and_submit(self):
        names = _names(get_tools_for_intent("escalate"))
        assert "escalate_to_sales" in names
        assert "submit_lead" in names

    def test_qualification_intent_offers_answer_faq(self):
        """The classifier defaults short/ambiguous messages to "qualification",
        so a mid-qualification pricing question must still be able to reach
        the pricing guardrail via answer_faq instead of the model improvising
        a price."""
        names = _names(get_tools_for_intent("qualification"))
        assert "answer_faq" in names
        assert "get_product_details" in names
        assert "submit_lead" not in names

    def test_lead_capture_intent_offers_submit_and_support_tools(self):
        names = _names(get_tools_for_intent("lead_capture"))
        assert names == {
            "capture_lead_info",
            "submit_lead",
            "escalate_to_sales",
            "get_product_details",
            "answer_faq",
        }

    def test_greeting_intent_offers_solution_content(self):
        names = _names(get_tools_for_intent("greeting"))
        assert "get_solution_content" in names

    def test_unknown_intent_falls_back_to_all_tools(self):
        """An intent the classifier could theoretically emit but that isn't
        wired into intent_tools must fail open to the full toolset, not
        fail closed to zero tools."""
        names = _names(get_tools_for_intent("some_future_intent_not_yet_mapped"))
        assert names == _names(get_all_tools())
