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
import re
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

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
from .tools.registry import get_tools_for_intent, GET_PRODUCT_DETAILS_TOOL
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

# User-facing labels for the "progress" SSE event (see process_message_stream)
# — shown as a transient status line while a tool call is in flight, so the
# wait isn't a silent typing indicator.
_TOOL_PROGRESS_LABELS: Dict[str, str] = {
    "search_products": "Searching products...",
    "get_product_details": "Checking specs...",
    "get_solution_content": "Pulling up details...",
    "answer_faq": "Looking that up...",
    "submit_lead": "Saving your info...",
    "escalate_to_sales": "Connecting you with sales...",
    "capture_lead_info": "Noting that down...",
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
    for event in _process_turn(message, session, stream=False):
        if event["type"] == "done":
            return event["response"]
    # _process_turn always ends with a "done" event — see its docstring.
    raise RuntimeError("agent loop ended without producing a response")


def process_message_stream(message: str, session: ConversationSession) -> Iterator[Dict[str, Any]]:
    """
    Same agentic loop as process_message, but also yields "progress" events
    (a tool call started/finished — shown as a transient status line) and
    "token" events (incremental text of the final round) as they happen,
    for the SSE endpoint (routers/chat.py's /api/chat/stream) to forward to
    the client. The last event is always {"type": "done", "response": ...},
    carrying the same ChatResponse process_message would have returned.
    """
    yield from _process_turn(message, session, stream=True)


def _process_turn(message: str, session: ConversationSession, stream: bool) -> Iterator[Dict[str, Any]]:
    """
    Shared implementation behind process_message and process_message_stream.

    Always ends by yielding exactly one {"type": "done", "response": ChatResponse}
    event, after any number of "progress"/"token" events. When stream=False,
    the LLM call itself is never streamed (so mocking
    client.chat.completions.create's return value in tests works exactly as
    before) and no "token" events are produced — only process_message_stream
    passes stream=True.
    """
    trace = ReasoningTrace(turn_id=f"turn-{session.turn_count}")

    # ── 1 & 2. Classify intent and extract slots concurrently ──
    # Both are independent OpenAI calls on the raw message — classify_intent
    # never touches session state, extract_slots never touches intent — so
    # running them sequentially was a free round-trip left on the table.
    # process_message is sync end-to-end, so a thread pool (not
    # asyncio.gather) is the minimal way to overlap the two blocking calls.
    with ThreadPoolExecutor(max_workers=2) as executor:
        intent_future = executor.submit(classify_intent, message)
        slots_future = executor.submit(extract_slots, message, session.collected_info)
        intent, confidence, _ = intent_future.result()
        new_info = slots_future.result()

    session.intent = intent
    trace.intent_classified(intent, confidence, {})
    logger.info("Turn %d — intent: %s", session.turn_count, intent)
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
        yield {"type": "done", "response": ChatResponse(
            type="clarification",
            text=text,
            new_info=new_info,
            next_state=determine_next_state(session.collected_info),
        )}
        return

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
        yield {"type": "done", "response": ChatResponse(
            type="clarification",
            text=text,
            ui_actions=["offer_booking"],
            new_info=new_info,
            next_state=ConversationState.HANDOFF,
        )}
        return

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
        yield {"type": "done", "response": ChatResponse(
            type="clarification",
            text=text,
            new_info=new_info,
            next_state=determine_next_state(session.collected_info),
        )}
        return

    # ── 4. Build the agent loop ──
    tools = get_tools_for_intent(intent)
    # get_tools_for_intent("faq") doesn't include get_product_details — by
    # design, FAQ turns don't need it. But a message naming a specific
    # product (checked deterministically, same pattern as the FAQ-shortcut
    # bypass above) is a spec question regardless of classified intent, and
    # the model can't call a tool it was never offered — this isn't a
    # prompt-wording problem, the tool was structurally unavailable. Found
    # live: intent classified "faq" for "does the VP6300 support WiFi and
    # Cellular?", and the model answered from its own guess instead of
    # get_product_details, since that tool wasn't in its list at all.
    if _PRODUCT_NAME_PATTERN.search(message.lower()) and not any(
        t["function"]["name"] == "get_product_details" for t in tools
    ):
        tools = tools + [GET_PRODUCT_DETAILS_TOOL]
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

    # timeout + max_retries are explicit (not SDK defaults) so a slow/flaky
    # OpenAI call fails predictably within a demo-acceptable window instead
    # of hanging the request indefinitely. The SDK itself retries transient
    # errors (connection errors, 429, 5xx) with backoff up to max_retries.
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY"),
        timeout=20.0,
        max_retries=2,
    )

    def _safe_fallback() -> ChatResponse:
        """Safe degraded response — used both when MAX_TOOL_ROUNDS is
        exhausted and when the OpenAI call fails outright (timeout, rate
        limit, connection error, etc). Never lets a call-site exception
        propagate up to the router as a raw 500."""
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

    for round_num in range(MAX_TOOL_ROUNDS):
        tool_choice = "auto" if not lead_submitted_this_turn else "none"
        if stream:
            try:
                chunk_stream = client.chat.completions.create(
                    model="gpt-4o",
                    tools=tools,
                    tool_choice=tool_choice,
                    messages=messages,
                    stream=True,
                )
            except OpenAIError:
                logger.exception("OpenAI call failed on turn %d, round %d", session.turn_count, round_num)
                yield {"type": "done", "response": _safe_fallback()}
                return

            # Accumulate content and tool-call chunks. finish_reason == "tool_calls"
            # rounds don't normally carry content, so content deltas can be
            # forwarded live as "token" events without knowing in advance
            # whether this ends up being the final (text) round or a
            # tool-call round — see ARCHITECTURE.md / Package F notes.
            content_parts: List[str] = []
            tool_calls_acc: Dict[int, Dict[str, str]] = {}
            finish_reason: Optional[str] = None
            for chunk in chunk_stream:
                delta = chunk.choices[0].delta
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
                if delta.content:
                    content_parts.append(delta.content)
                    yield {"type": "token", "delta": delta.content}
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        acc = tool_calls_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                        if tc.id:
                            acc["id"] = tc.id
                        if tc.function and tc.function.name:
                            acc["name"] += tc.function.name
                        if tc.function and tc.function.arguments:
                            acc["arguments"] += tc.function.arguments

            reply_tool_calls = [
                SimpleNamespace(id=acc["id"], function=SimpleNamespace(name=acc["name"], arguments=acc["arguments"]))
                for _, acc in sorted(tool_calls_acc.items())
            ] or None
            reply_message = SimpleNamespace(content="".join(content_parts) or None, tool_calls=reply_tool_calls)
        else:
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    tools=tools,
                    tool_choice=tool_choice,
                    messages=messages,
                )
            except OpenAIError:
                logger.exception("OpenAI call failed on turn %d, round %d", session.turn_count, round_num)
                yield {"type": "done", "response": _safe_fallback()}
                return

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

            yield {"type": "done", "response": ChatResponse(
                type=resp_type,  # type: ignore
                text=final_text,
                recommendation=recommendation,
                quick_replies=["Yes, connect me", "Not yet"] if products_this_turn and not session.lead_submitted else None,
                ui_actions=ui_actions,
                new_info=new_info,
                next_state=next_state,
            )}
            return

        # ── Handle tool calls ──
        # A plain dict (not the raw SDK message object) so the streaming
        # path's SimpleNamespace stand-in serializes the same way the
        # non-streaming path's real ChatCompletionMessage does.
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": reply_message.content}
        if reply_message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in reply_message.tool_calls
            ]
        messages.append(assistant_msg)

        for tool_call in reply_message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            tool_names_used.append(tool_name)
            trace.tool_called(tool_name, tool_args)
            yield {
                "type": "progress",
                "stage": "tool_call",
                "tool": tool_name,
                "message": _TOOL_PROGRESS_LABELS.get(tool_name, "Working on it..."),
            }

            # Execute the tool
            result_str = _dispatch_tool(tool_name, tool_args, session)
            result = json.loads(result_str)

            trace.tool_result(tool_name, result_str[:200])
            yield {"type": "progress", "stage": "tool_result", "tool": tool_name}

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
    yield {"type": "done", "response": _safe_fallback()}


# ── Helpers ─────────────────────────────────────────────────────────────

_FAQ_KEYWORDS: Dict[str, List[str]] = {
    "pricing": ["price", "cost", "pricing", "quote", "how much", "budget", "rate", "cheap", "expensive", "discount"],
    "shipping": ["shipping", "delivery", "ship", "lead time", "how long", "arrive"],
    "warranty": ["warranty", "guarantee", "coverage", "repair", "replace", "broken", "defect"],
    "returns": ["return", "refund", "money back", "send back", "exchange"],
    "compatibility": ["compatible", "work with", "integrate", "integration", "platform", "software"],
    "security": ["security", "secure", "PCI", "encryption", "compliance", "certified", "tamper"],
    "support": ["support", "help", "technical support", "contact", "phone", "call", "reach"],
    "payment_integration": ["pae", "payment application engine", "middleware", "emv certification", "level 3", "l3", "processor integration", "tokenization"],
    "device_management": ["rdm", "remote device management", "firmware", "fleet", "remote update", "device monitoring", "diagnostics"],
    "key_injection": ["rki", "key injection", "remote key", "cryptographic key", "key provisioning"],
    "merchant_services": ["merchant services", "merchant account", "processing", "p2pe", "interchange", "acquirer", "gateway", "echeck", "ach", "virtual terminal", "invoicing", "payment link", "boarding", "onboarding"],
}

# Model-name shapes seen across the catalog (VP3300, AP3880P, Kiosk IV,
# SmartPIN L80, SREDKey2, MiniMag II, ...). A message naming a specific
# product is a spec question, not a FAQ — it needs the full agent loop and
# get_product_details, not the keyword-matched canned-answer shortcut below.
# `\s?` between prefix and digits tolerates a stray space ("vp 6300") —
# without it, a message differing from the real bypass trigger by exactly
# one space silently fell back through to the FAQ shortcut (found live:
# "does the vp 6300 support wifi?" got generic compatibility boilerplate
# instead of ever reaching get_product_details).
_PRODUCT_NAME_PATTERN = re.compile(
    r"\b(vp\s?\d{3,4}\w*|ap\s?\d{3,4}\w*|kiosk\s*(iv|v|iii)\b|smartpin(\s*l\d+)?|sredkey\s*\d*|minimag(\s*(ii|duo))?|minismart(\s*ii)?)\b",
    re.IGNORECASE,
)

# Spec/capability terms that mean "support" is being used as a verb ("does
# it support NFC?") rather than a request for customer help.
_CONNECTIVITY_TERMS = (
    "wifi", "wi-fi", "cellular", "bluetooth", "ethernet", "usb", "nfc",
    "emv", "contactless", "magstripe", "rs232", "serial", "pin",
)


def _has_only_faq_intent(message: str) -> bool:
    """Check if the message is purely a FAQ question (not mixed with qualification)."""
    lower = message.lower().strip()
    # A message naming a specific product is a spec question, not a FAQ —
    # route it to the full agent loop so get_product_details can answer with
    # real specs instead of a generic canned answer (see loop.py history:
    # "does the VP6300 support WiFi and Cellular?" was misrouted here before
    # this check existed).
    if _PRODUCT_NAME_PATTERN.search(lower):
        return False
    # If it's very short and purely a question, treat as pure FAQ
    if len(lower) < 80 and lower.count("?") <= 2:
        return True
    return False


def _kw_in(lower: str, kw: str) -> bool:
    """Word-boundary keyword match, not plain substring: merchant_services'
    "ach" keyword would otherwise false-positive on "reach", "each",
    "coach", "teach", etc. — a plain `kw in lower` check can't tell
    "ACH?" from "how do I reach support?".

    The optional `(s|es)` suffix keeps plurals working. A bare `\\b<kw>\\b`
    regressed pre-existing singular keywords that used to match by
    substring: "rate" stopped matching "what are your rates?", "return"
    stopped matching "do you have returns", and "integration" stopped
    matching "what integrations do you have" — all of which silently fell
    through to the "general" topic. A broader `\\w*` suffix would fix those
    but reintroduce the original bug ("ach" would match "achieve"), so the
    suffix is deliberately limited to plural forms.
    """
    return re.search(r"\b" + re.escape(kw.lower()) + r"(s|es)?\b", lower) is not None


def _detect_faq_topic(message: str) -> str:
    """Detect which FAQ topic the user is asking about."""
    lower = message.lower()
    # "does/is/can it support <spec>" is a compatibility question, not a
    # request for customer support — check this before the generic keyword
    # loop, where bare "support" would otherwise win.
    if "support" in lower and any(_kw_in(lower, term) for term in _CONNECTIVITY_TERMS):
        return "compatibility"
    # Same problem, merchant-services shaped: "do you support ACH?" would
    # otherwise hit the generic "support" keyword (checked earlier in
    # _FAQ_KEYWORDS) before ever reaching merchant_services' own keywords.
    if "support" in lower and any(_kw_in(lower, term) for term in _FAQ_KEYWORDS["merchant_services"]):
        return "merchant_services"
    for topic, keywords in _FAQ_KEYWORDS.items():
        for kw in keywords:
            if _kw_in(lower, kw):
                return topic
    return "general"
