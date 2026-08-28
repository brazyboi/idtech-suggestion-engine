"""
Agentic loop — the core orchestration engine.

Replaces the old slot-planner-driven ChatService with an LLM-driven agent
that can search products, answer FAQs, capture leads, and escalate.

Flow per turn:
1. Classify intent (gpt-4o-mini)
2. Build tool list based on intent
3. Passively extract qualification/lead info from the user message
4. Call LLM (gpt-4o) with system prompt + tools + history
5. Execute any tool calls
6. If tools were called, call LLM again with tool results to formulate response
7. Build and return ChatResponse
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from ..engine.state_machine import (
    CollectedInfo,
    ConversationSession,
    ConversationState,
    determine_next_state,
)
from ..engine.solution_schemas import (
    HardwareRecommendation,
    RecommendationBundle,
    InstallationDoc,
)
from ..llm.contracts import ChatResponse
from ..services.logger import ReasoningTrace
from .classifier import classify_intent
from .prompts import build_system_prompt
from .slot_extractor import extract_slots
from .tools.registry import get_tools_for_intent
from .tools._product_url import get_product_url
from .tools.search_products import search_products as _search_products
from .tools.get_product_details import get_product_details as _get_product_details
from .tools.get_solution_content import get_solution_content as _get_solution_content
from .tools.answer_faq import answer_faq as _answer_faq
from .tools.submit_lead import submit_lead as _submit_lead
from .tools.escalate_to_sales import escalate_to_sales as _escalate_to_sales
from .tools.capture_lead_info import capture_lead_info as _capture_lead_info

load_dotenv()
logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5  # Safety limit — prevent infinite tool loops


# ── Tool Dispatcher ─────────────────────────────────────────────────────

TOOL_MAP: Dict[str, Any] = {
    "search_products": _search_products,
    "get_product_details": _get_product_details,
    "get_solution_content": _get_solution_content,
    "answer_faq": _answer_faq,
    "submit_lead": _submit_lead,
    "escalate_to_sales": _escalate_to_sales,
    "capture_lead_info": _capture_lead_info,
}


def _dispatch_tool(tool_name: str, arguments: Dict[str, Any], session: ConversationSession) -> str:
    """
    Execute a tool and return its result as a JSON string.

    Injects the session into tools that need it (submit_lead, escalate_to_sales, capture_lead_info).
    """
    fn = TOOL_MAP.get(tool_name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # Inject session for tools that need it
    if tool_name in ("submit_lead", "escalate_to_sales", "capture_lead_info"):
        arguments["session"] = session

    try:
        result = fn(**arguments)
        return json.dumps(result)
    except Exception as e:
        logger.exception("Tool '%s' failed", tool_name)
        return json.dumps({"error": f"Tool '{tool_name}' failed: {str(e)}"})


# ── Product Recommendation Builder ──────────────────────────────────────

def _build_recommendation(products_data: List[Dict[str, Any]]) -> Optional[RecommendationBundle]:
    """Build a RecommendationBundle from search_products results."""
    if not products_data:
        return None

    items = []
    for p in products_data[:3]:
        items.append(HardwareRecommendation(
            name=p.get("model_name", "Unknown"),
            role="Recommended",
            technical_specs=p.get("key_specs", {}),
            product_url=p.get("product_url"),
        ))

    if not items:
        return None

    top = products_data[0]
    highlights = top.get("highlights", [])
    specs = top.get("key_specs", {})

    evidence = []
    for label, field in [("Power", "input_power"), ("Interface", "interface"),
                         ("Temp Range", "operate_temperature"), ("IP Rating", "ip_rating")]:
        val = specs.get(field)
        if val:
            evidence.append(f"{label}: {val}")

    explanation = (
        f"Based on your requirements, I recommend the {items[0].name}. "
        f"It matches on: {', '.join(evidence)}. "
        f"This device is suitable for your deployment needs."
        if evidence else
        f"Based on your requirements, I recommend the {items[0].name}."
    )

    from ..engine.solution_schemas import SoftwareRecommendation

    software_list = [
        SoftwareRecommendation(name=s)
        for s in (top.get("compatible_software", []) or [])
    ]

    # Fetch installation docs for the top product
    docs = []
    try:
        from ..engine.product_matcher import ProductMatcher
        fetched = ProductMatcher._fetch_installation_docs(items[0].name)
        if fetched:
            docs = [doc.model_dump() for doc in fetched]
    except Exception:
        pass

    return RecommendationBundle(
        hardware_name=items[0].name,
        hardware_items=items,
        software=software_list,
        highlights=highlights,
        explanation=explanation,
        installation_docs=docs,
    )


# ── Main Loop ───────────────────────────────────────────────────────────

def process_message(message: str, session: ConversationSession) -> ChatResponse:
    """
    Process a single user message through the full agentic loop.

    Args:
        message: The user's current message.
        session: Mutable deep copy of the conversation session.
                 Mutated in-place — caller must save afterward.

    Returns:
        A ChatResponse with the assistant's reply and any structured data.
    """
    trace = ReasoningTrace(turn_id=f"turn-{session.turn_count}")

    # ── 1. Classify intent ──
    intent, confidence, _ = classify_intent(message)
    session.intent = intent
    trace.intent_classified(intent, confidence, {})
    logger.info("Turn %d — intent: %s", session.turn_count, intent)

    # ── 2. Passively extract slots from this message ──
    new_info = extract_slots(message, session.collected_info)
    if new_info:
        logger.info("Extracted: %s", new_info)

    # ── 3. Early routes (no agent loop needed) ──
    if intent == "faq" and _has_only_faq_intent(message):
        # Direct FAQ answer without full agent loop
        result = _answer_faq(topic=_detect_faq_topic(message))
        text = result.get("answer", "A sales rep can help with that. Would you like me to connect you?")
        trace.response_generated("clarification", text)
        session.history.append({"role": "user", "content": message})
        session.history.append({"role": "assistant", "content": text})
        session.turn_count += 1
        return ChatResponse(
            type="clarification",
            text=text,
            new_info=new_info,
            next_state=determine_next_state(session.collected_info),
        )

    if intent == "escalate":
        contact = {
            "name": session.collected_info.lead.name,
            "email": session.collected_info.lead.email,
        }
        result = _escalate_to_sales(
            reason="Prospect requested to speak with a sales representative.",
            session=session,
        )
        text = result.get("message", "A member of our sales team will reach out shortly.")
        trace.response_generated("clarification", text)
        session.history.append({"role": "user", "content": message})
        session.history.append({"role": "assistant", "content": text})
        session.turn_count += 1
        return ChatResponse(
            type="clarification",
            text=text,
            ui_actions=["offer_booking"],
            new_info=new_info,
            next_state=ConversationState.HANDOFF,
        )

    if intent == "chitchat":
        # Build a context-aware redirect based on what's been collected so far
        collected = session.collected_info
        if collected.environment.vertical:
            text = (
                f"Let's focus on your {collected.environment.vertical} setup. "
                "I'm here to help find the right payment hardware — "
                "what specific questions do you have about your deployment?"
            )
        elif session.history:
            text = (
                "I'm here to help with ID TECH payment hardware. "
                "Tell me about the kind of payment solution you're looking for, "
                "and I'll help find the right match."
            )
        else:
            text = "I can help find the right payment hardware for your business. What industry or use case are you working on?"

        trace.response_generated("clarification", text)
        session.history.append({"role": "user", "content": message})
        session.history.append({"role": "assistant", "content": text})
        session.turn_count += 1
        return ChatResponse(
            type="clarification",
            text=text,
            new_info=new_info,
            next_state=determine_next_state(session.collected_info),
        )

    # ── 4. Build the agent loop ──
    tools = get_tools_for_intent(intent)
    tool_names_used: List[str] = []
    products_this_turn: List[Dict[str, Any]] = []
    lead_submitted_this_turn = False

    # Build system prompt
    system_prompt = build_system_prompt(session)

    # Build message list
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    # Add conversation history (last 20 messages to stay within context)
    for msg in session.history[-20:]:
        messages.append(msg)
    messages.append({"role": "user", "content": message})

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY") or "test-key")

    for round_num in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model="gpt-4o",
            tools=tools if tool_names_used else tools,  # Keep tools available
            tool_choice="auto" if not lead_submitted_this_turn else "none",
            messages=messages,
        )

        choice = response.choices[0]
        reply_message = choice.message
        finish_reason = choice.finish_reason

        # Log the trace
        trace.tool_called(reply_message.content or "(no content)", {})

        # No tool call — final response
        if finish_reason == "stop" or not reply_message.tool_calls:
            final_text = reply_message.content or ""

            # Log response
            trace.response_generated(
                "recommendation" if products_this_turn else "clarification",
                final_text,
            )

            # Append to history
            session.history.append({"role": "user", "content": message})
            session.history.append({"role": "assistant", "content": final_text})
            session.turn_count += 1
            trace.log_to_console()

            # Build the response type
            resp_type: str = "recommendation" if products_this_turn else "clarification"

            # Build recommendation bundle if we have products
            recommendation = _build_recommendation(products_this_turn) if products_this_turn else None

            # Determine next state
            next_state = determine_next_state(session.collected_info)

            # UI actions
            ui_actions: List[str] = []
            if lead_submitted_this_turn or session.lead_submitted:
                ui_actions = ["offer_booking"]
            elif products_this_turn and not session.lead_submitted:
                ui_actions = ["show_products"]

            return ChatResponse(
                type=resp_type,  # type: ignore
                text=final_text,
                recommendation=recommendation,
                quick_replies=["Yes, connect me", "Not yet"] if products_this_turn and not session.lead_submitted else None,
                ui_actions=ui_actions,
                new_info=new_info,
                next_state=next_state,
            )

        # ── Handle tool calls ──
        messages.append(reply_message)  # Append assistant message with tool_calls

        for tool_call in reply_message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            tool_names_used.append(tool_name)
            trace.tool_called(tool_name, tool_args)

            # Execute the tool
            result_str = _dispatch_tool(tool_name, tool_args, session)
            result = json.loads(result_str)

            trace.tool_result(tool_name, result_str[:200])

            # Collect structured data from results
            if tool_name == "search_products" and "products" in result:
                products_this_turn = result["products"]
                # Store recommended product names in session
                for p in products_this_turn:
                    name = p.get("model_name", "")
                    if name and name not in session.recommended_products:
                        session.recommended_products.append(name)
                # Signal that recommendations have been shown for stage transitions
                if products_this_turn:
                    session.collected_info.meta.recommendation_shown = True

            if tool_name == "submit_lead" and result.get("status") == "submitted":
                lead_submitted_this_turn = True
                session.lead_submitted = True

            if tool_name == "escalate_to_sales" and result.get("status") == "escalated":
                session.lead_submitted = True

            # Append tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_str,
            })

    # ── MAX_TOOL_ROUNDS reached — safe fallback ──
    fallback = (
        "I'm having trouble processing that right now. Could you rephrase, "
        "or would you like me to connect you with our team directly?"
    )
    trace.response_generated("clarification", fallback)
    session.history.append({"role": "user", "content": message})
    session.history.append({"role": "assistant", "content": fallback})
    session.turn_count += 1
    trace.log_to_console()

    return ChatResponse(
        type="clarification",
        text=fallback,
        new_info=new_info,
        next_state=ConversationState.QUALIFYING,
    )


# ── Helpers ─────────────────────────────────────────────────────────────

_FAQ_KEYWORDS: Dict[str, List[str]] = {
    "pricing": ["price", "cost", "pricing", "quote", "how much", "budget", "rate", "cheap", "expensive", "discount"],
    "shipping": ["shipping", "delivery", "ship", "lead time", "how long", "arrive"],
    "warranty": ["warranty", "guarantee", "coverage", "repair", "replace", "broken", "defect"],
    "returns": ["return", "refund", "money back", "send back", "exchange"],
    "compatibility": ["compatible", "work with", "integrate", "integration", "platform", "software"],
    "security": ["security", "secure", "PCI", "encryption", "compliance", "certified", "tamper"],
    "support": ["support", "help", "technical support", "contact", "phone", "call", "reach"],
}


def _has_only_faq_intent(message: str) -> bool:
    """Check if the message is purely a FAQ question (not mixed with qualification)."""
    lower = message.lower().strip()
    # If it's very short and purely a question, treat as pure FAQ
    if len(lower) < 80 and lower.count("?") <= 2:
        return True
    return False


def _detect_faq_topic(message: str) -> str:
    """Detect which FAQ topic the user is asking about."""
    lower = message.lower()
    for topic, keywords in _FAQ_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return topic
    return "general"
