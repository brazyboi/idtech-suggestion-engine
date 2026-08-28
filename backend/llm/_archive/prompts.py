from typing import List, Dict, Any, Optional

# ── Slot-bound prompt template ───────────────────────────────────────────
# When a planned_slot is provided the LLM is constrained to phrase ONLY
# a question about that specific slot.  The backend decides what to ask.

SLOT_BOUND_SYSTEM_PROMPT = """
You are the IDTECH Helper Agent — a warm, friendly sales engineer helping a
customer find the right payment hardware.

CURRENT TOPIC: {slot_prompt_hint}

{next_topic_hint}

RULES:
1. Ask exactly ONE natural question per response.
2. If a question has structured answers (options), call `present_choices`
   with the slot "{slot_id}" and 2-4 clear options that directly answer
   your question.
3. Never ask about pricing, quotes, or product names.
4. Never mention "lead" or "lead capture" — use "contact details" instead.

CONVERSATION FLOW:
- If the user's most recent message answers your question, use the
  available tool to save their answer silently (do NOT mention the tool).
- If the user also mentioned something off-topic, use the extra-info tool
  to save it (again, silently).
- If you have NOT yet asked about the CURRENT TOPIC, ask now.
- If the user HAS answered the current topic, acknowledge briefly and move
  naturally to the NEXT TOPIC shown above.
- Always write your reply first, then call any tools.
- Never produce closing remarks like "feel free to ask" or "let me know
  if you have questions" — the conversation continues.

{known_summary}

STYLE:
- Be warm and conversational, like a helpful colleague.
- Never mention tools, capturing, recording, or internal processes.
- Never apologize for asking a question — just ask it.
- Keep it brief: acknowledge in one short sentence, then ask.
""".strip()


STATE_PROMPTS = {
    "greeting": """
You are an ID TECH sales engineer starting a conversation with a potential customer.

Your job:
- Be warm, friendly, and helpful. Introduce yourself as the IDTECH Helper Agent.
- Start with an open-ended greeting like "Hi! How can I help you today?" — do NOT immediately ask for their business vertical.
- If they express interest in finding a product or payment solution, then ask what kind of business they run (vertical/industry) — parking, transit, vending, retail, EV charging, etc.
- Only ask about the business vertical AFTER they've indicated interest.
- Ask ONE question at a time. Do NOT ask about indoor/outdoor, technical details, or anything else yet.
- Do NOT ask broad discovery questions like "Are you looking for specific features or capabilities?"
- After vertical is known, the next qualification question should be concrete and scoped (for example, indoor vs outdoor), not open-ended.
- Never mention pricing, quotes, or specific product names.
- If the user is just browsing or asking general questions, be helpful without pushing for qualification.
- Ask exactly ONE question per message (never a list of questions).
- NEVER use the words "lead" or "lead capture" with the customer. Say "contact details" or "your information" instead.

CRITICAL RULES (follow them in order):
1. Whenever the user provides new information (vertical, indoor/outdoor, temperature, etc.), you MUST call the available extraction tool to capture it as structured data. This is the ONLY way the system remembers.
2. After asking a question where specific answers make sense, call `present_choices` to offer clickable quick-reply buttons. This helps the user respond quickly.
3. You can call BOTH tools in the same response — first capture the data, then `present_choices` to offer follow-up options.
4. Always write your conversational reply in the message content first, then call the tools.
""",

    "environment": """
You are helping qualify the deployment environment.

Focus on gathering:
1. **Indoor vs outdoor** — and if outdoor, rough temperature range (e.g., 0C to 40C indoor, -20C to 65C outdoor, -30C to 70C harsh outdoor).
2. Any weather/durability concerns (rain, dust, vandalism).

Be conversational — ask exactly one thing at a time.
Never discuss pricing, quotes, or product names.
NEVER use the words "lead" or "lead capture" with the customer.
""",

    "transaction_profile": """
You are gathering transaction volume information.

Focus on:
1. How many transactions per month they expect.
2. Average transaction value (if they're willing to share).

This helps determine if they need a high-throughput or enterprise-grade solution.
Keep it light — "just a rough idea is fine."
Ask exactly ONE question per message (never stack multiple asks).
Never discuss pricing, quotes, or product names.
NEVER use the words "lead" or "lead capture" with the customer.
""",

    "recommendation": """
The backend has already prepared a product recommendation. Your job is simply to present it to the user in a clear, enthusiastic way.

Rules:
- Do NOT generate product names or specs yourself — the backend handles that.
- Use the information provided in the system message to explain the recommendation.
- Ask if they'd like to download the recommendation as a PDF.
- Transition to asking for their contact information (name, email) so we can follow up.
- Ask exactly ONE question per message.
- NEVER use the words "lead" or "lead capture" with the customer.

Use the available extraction tool to capture any contact details the user provides.
""",

    "lead_capture": """
The user is ready to share their contact information. Be friendly and professional.

Ask for:
1. Name
2. Email
3. Company name
4. Phone (optional)

Let them know a specialist will follow up with more details.
Never discuss pricing, quotes, or specific product names.
Ask exactly ONE question per message.
NEVER use the words "lead" or "lead capture" with the customer.

Use the available extraction tool to capture the user's answers.
""",

    "complete": """
Thank the user for their time. Let them know:
- A specialist will reach out to them.
- They can download the recommendation PDF.
- Offer to book a meeting with a sales engineer if they'd like.

Keep it warm and professional. Your job here is done.
NEVER use the words "lead" or "lead capture" with the customer.
""",
}


PRESENT_CHOICES_TOOL = {
    "type": "function",
    "function": {
        "name": "present_choices",
        "description": "Suggest clickable quick-reply buttons for the user. Call this AFTER asking a question that has a set of common or expected answers. The buttons let the user respond with a single tap instead of typing. IMPORTANT: choices must directly answer your exact question; do not use generic Yes/No unless the question itself is strictly yes/no.",
        "parameters": {
            "type": "object",
            "properties": {
                "slot": {
                    "type": "string",
                    "description": "The slot identifier this question belongs to. Must match the planned slot exactly."
                },
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of answer options to show as buttons (2–4 options, short and clear)"
                }
            },
            "required": ["slot", "choices"]
        }
    }
}


CAPTURE_ADDITIONAL_INFO_TOOL = {
    "type": "function",
    "function": {
        "name": "capture_additional_info",
        "description": (
            "Save extra info the user volunteers beyond the current topic. "
            "Use when the user mentions business, environment, technical, or contact "
            "details that aren't the main topic this turn. "
            "Do NOT use for the main topic \u2014 use the dedicated extract_* tool. "
            "Example: user says 'it will be outdoors' during a vertical question \u2192 "
            "section='environment', field='indoor_outdoor', value='outdoor'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["environment", "transaction_profile", "technical_context", "lead"],
                    "description": "The section this information belongs to."
                },
                "field": {
                    "type": "string",
                    "description": (
                        "The field name within the section. Use snake_case, e.g. "
                        "'indoor_outdoor', 'card_types', 'needs_pin', 'monthly_volume', "
                        "'name', 'email'."
                    )
                },
                "value": {
                    "type": "string",
                    "description": (
                        "The value for this field. Use a clear string representation "
                        "(e.g. 'outdoor', '5000', 'contactless', 'John')."
                    )
                }
            },
            "required": ["section", "field", "value"],
            "additionalProperties": False
        }
    }
}


def build_tools_for_planned_slot(slot_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Build the tool list for a given planned slot.

    Returns a list containing:
    1. A slot-specific extraction tool that ONLY accepts that slot's field(s)
    2. The `present_choices` tool for offering quick-reply buttons

    When slot_id is None (no planned slot), returns only `present_choices`.
    """
    if not slot_id:
        return [PRESENT_CHOICES_TOOL]

    from ..engine.slot_planner import SLOT_BY_ID, SlotParser

    slot = SLOT_BY_ID.get(slot_id)
    if not slot:
        return [PRESENT_CHOICES_TOOL]

    # Parse the dotted path: "environment.vertical" -> section="environment", field="vertical"
    parts = slot.path.split(".")
    if len(parts) != 2:
        return [PRESENT_CHOICES_TOOL]

    section, field = parts

    # Build the field property based on parser type
    if slot.parser == SlotParser.BOOLEAN:
        prop: Dict[str, Any] = {
            "type": "boolean",
            "description": f"User's yes/no answer for: {slot.prompt_hint}",
        }
    elif slot.parser == SlotParser.NUMBER:
        prop = {
            "type": "integer",
            "description": f"User's numeric answer for: {slot.prompt_hint}",
        }
    elif slot.parser == SlotParser.CHOICE:
        desc = slot.prompt_hint
        options_hint = f" Options: {', '.join(slot.allowed_choices)}" if slot.allowed_choices else ""
        prop = {
            "type": "string",
            "description": f"User's answer for: {desc}.{options_hint}",
        }
    elif slot.parser in (SlotParser.FREE_TEXT, SlotParser.VOLUME_TICKET):
        prop = {
            "type": "string",
            "description": f"User's response for: {slot.prompt_hint}",
        }
    else:
        prop = {"type": "string", "description": f"User's response for: {slot.prompt_hint}"}

    tool_name = f"extract_{slot_id}"

    extraction_tool = {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": (
                f"Save the user's answer about {slot.prompt_hint.lower()}. "
                "Call this when the user provides information about this topic."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    section: {
                        "type": "object",
                        "properties": {
                            field: prop,
                        },
                        "required": [field],
                        "additionalProperties": False,
                        "description": f"Section containing the {field} field.",
                    }
                },
                "required": [section],
                "additionalProperties": False,
            },
        },
    }

    return [extraction_tool, CAPTURE_ADDITIONAL_INFO_TOOL, PRESENT_CHOICES_TOOL]


def build_known_summary(collected_info: Dict[str, Any] | None) -> str:
    """Build a [Already known] summary block so the LLM doesn't re-ask."""
    if not collected_info:
        return ""

    known_parts = []
    env = collected_info.get("environment", {})
    tc = collected_info.get("technical_context", {})
    tp = collected_info.get("transaction_profile", {})
    lead = collected_info.get("lead", {})

    if env.get("vertical"):
        known_parts.append(f"Vertical: {env['vertical']}")
    if env.get("indoor_outdoor"):
        known_parts.append(f"Environment: {env['indoor_outdoor']}")
    if env.get("temperature_range"):
        known_parts.append(f"Temp: {env['temperature_range']}")
    if tc.get("card_types"):
        known_parts.append(f"Cards: {', '.join(tc['card_types'])}")
    if tc.get("needs_pin") is not None:
        known_parts.append(f"PIN: {'yes' if tc.get('needs_pin') else 'no'}")
    if tc.get("power_source"):
        known_parts.append(f"Power: {tc['power_source']}")
    if tc.get("voltage"):
        known_parts.append(f"Voltage: {tc['voltage']}")
    if tc.get("is_standalone") is not None:
        known_parts.append(f"Standalone: {tc['is_standalone']}")
    if tc.get("host_interface"):
        known_parts.append(f"Interface: {tc['host_interface']}")
    if tc.get("standalone_comms"):
        known_parts.append(f"Comms: {tc['standalone_comms']}")
    if tc.get("needs_display") is not None:
        known_parts.append(f"Display: {tc['needs_display']}")
    if tc.get("previous_products"):
        known_parts.append(f"Previous: {', '.join(tc['previous_products'])}")
    if tp.get("monthly_volume") is not None:
        known_parts.append(f"Volume: {tp['monthly_volume']}/mo")
    if tp.get("average_ticket") is not None:
        known_parts.append(f"Avg ticket: ${tp['average_ticket']}")
    if lead.get("name"):
        known_parts.append(f"Contact: {lead['name']}")
    if lead.get("email"):
        known_parts.append(f"Email: {lead['email']}")

    if known_parts:
        return "\n[Already known about this customer: " + "; ".join(known_parts) + "]\nDo NOT ask for this information again."
    return ""


def build_chat_prompt(
    message: str,
    history: List[Dict[str, str]],
    state: str = "greeting",
    collected_info: Dict[str, Any] = None,
    planned_slot_id: Optional[str] = None,
    slot_prompt_hint: Optional[str] = None,
    next_topic_hint: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Build the message list for the LLM call.

    When planned_slot_id and slot_prompt_hint are provided, uses the
    slot-bound prompt template so the LLM only phrases a question about
    that specific slot.

    Otherwise falls back to the legacy per-state prompts.
    """
    known_summary = build_known_summary(collected_info)

    if planned_slot_id and slot_prompt_hint:
        tool_name = f"extract_{planned_slot_id}"
        # Build the next-topic hint block (empty string when no next slot)
        formatted_next_hint = (
            f"NEXT TOPIC (ask this AFTER the customer answers the current one):\n{next_topic_hint}"
            if next_topic_hint else ""
        )
        system_content = SLOT_BOUND_SYSTEM_PROMPT.format(
            slot_id=planned_slot_id,
            slot_prompt_hint=slot_prompt_hint,
            known_summary=known_summary,
            tool_name=tool_name,
            next_topic_hint=formatted_next_hint,
        )
    else:
        state_prompt = STATE_PROMPTS.get(state, STATE_PROMPTS["greeting"])
        system_content = state_prompt.strip()
        system_content += (
            "\n\nGlobal style rules:\n"
            "- Ask exactly one question per assistant message.\n"
            "- Never present a checklist or multiple-question survey in one turn.\n"
            "- Avoid open-ended feature/capability questions; ask concrete, answerable questions with specific options.\n"
            "- Never call the customer a lead; use customer-friendly wording like "
            "'contact details' or 'your information'."
        )
        if known_summary:
            system_content += "\n" + known_summary

    messages = [{"role": "system", "content": system_content}]
    for msg in history:
        messages.append(msg)
    messages.append({"role": "user", "content": message})
    return messages