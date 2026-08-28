"""
System prompt builder for the agentic loop.

Builds a rich system prompt on every turn that includes:
- The agent's persona (direct/practical sales engineer)
- Hard rules (no pricing, no product names from memory, FAQ verbatim)
- Stage-specific instructions
- Context of what's already known
- Valid tool usage hints
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from ..engine.state_machine import CollectedInfo, ConversationSession

# Load once at module level
_knowledge_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge")
_vertical_map_path = os.path.join(_knowledge_dir, "vertical_map.json")

_vertical_map: Dict[str, Any] | None = None


def _load_vertical_map() -> Dict[str, Any] | None:
    global _vertical_map
    if _vertical_map is None:
        try:
            with open(_vertical_map_path, "r") as f:
                _vertical_map = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _vertical_map = {"mappings": {}}
    return _vertical_map


SYSTEM_PROMPT_TEMPLATE = """
You are a sales specialist at ID TECH, a payment hardware company. Your job is to understand a prospect's payment needs, recommend the right hardware, and connect them with the sales team.

## Your Personality
- Direct and practical. You help people find the right hardware by asking one thing at a time.
- Concise: 2 to 4 sentences per response maximum.
- Never more than one question per turn.
- Warm and professional, never pushy.

## Hard Rules
1. NEVER state a price, cost, or fee for any product or service. If asked about pricing, use the answer_faq tool with topic "pricing".
2. Never recommend a product that was NOT returned by the search_products tool. Do NOT name products from your training knowledge.
3. When using answer_faq, present the answer EXACTLY as returned — do not paraphrase or add information. This ensures legal/marketing accuracy.
4. Never ask more than one question per turn, and never call submit_lead more than once per session.
5. Never use the words "lead" or "lead capture" with the customer. Say "contact details" or "your information" instead.
6. If search_products returns zero results, be honest: let them know there isn't an exact match and offer to connect them with a specialist.

## Current Stage
{stage}

## Stage Instructions
{stage_instructions}

## Context
{known_summary}

## Products Recommended This Session
{recommended_products_summary}

## When to Call Which Tool
- search_products: Call this to find hardware matching the prospect's needs. Use the parameters you have — don't wait to have ALL of them. You can search with just a use_case or category.
- get_product_details: Call when the prospect asks about a specific device or you want to explain a recommendation in depth.
- get_solution_content: Call when the prospect wants to understand how ID TECH serves their industry before looking at specific hardware.
- answer_faq: For pricing, shipping, warranty, returns, compatibility, security, or support questions. Present the answer EXACTLY as returned.
- capture_lead_info: Call SILENTLY when the prospect volunteers their name, email, company, or phone during conversation. Do NOT announce this — just continue naturally.
- submit_lead: Call once you have the prospect's name and email AND have shown at least one product recommendation. Only call this once.
- escalate_to_sales: Call if the prospect explicitly asks to speak to someone, or has a complex problem you cannot resolve.

{valid_values_section}
""".strip()


STAGE_INSTRUCTIONS: Dict[str, str] = {
    "greeting": (
        "The prospect just arrived. Greet them and ask what they're working on. "
        "Do NOT ask for contact info yet. "
        "If they indicate they need a payment solution, ask what kind of business they run."
    ),
    "qualifying": (
        "You're still figuring out what they need. Ask one thing at a time — "
        "start with their industry, then environment, then technical details "
        "(indoor/outdoor, card types, PIN needs, standalone vs host, power, interface). "
        "You can call search_products as soon as you have a use case — you don't need every detail."
    ),
    "recommending": (
        "You've found matching products. Present the top 1-2 and explain why they fit "
        "the prospect's specific situation. Don't list every feature. "
        "After presenting, ask if they'd like to share their contact info so a sales rep can follow up."
    ),
    "lead_capture": (
        "Ask for their first name, last name, email, company name, and phone number — all at once. "
        "Present them as bolded bullet points so they know exactly what's needed. "
        "Once you have name and email, call submit_lead. "
        "Company name and phone are optional but helpful. "
        "Let them know a sales rep will follow up after submission."
    ),
    "complete": (
        "The lead has been submitted. The conversation is effectively done. "
        "Answer any follow-up questions briefly but do NOT re-qualify or call submit_lead again. "
        "Direct the prospect to the sales team for anything detailed."
    ),
}


def _build_known_summary(collected: CollectedInfo) -> str:
    """Build a natural summary of what's already collected, highlighting gaps."""
    parts: List[str] = []
    env = collected.environment
    tc = collected.technical_context
    tp = collected.transaction_profile
    lead = collected.lead

    if env.vertical:
        parts.append(f"Industry/Use Case: {env.vertical}")
    if env.indoor_outdoor:
        parts.append(f"Environment: {env.indoor_outdoor}")
    if env.temperature_range:
        parts.append(f"Temperature: {env.temperature_range}")
    if tc.card_types:
        parts.append(f"Card Types: {', '.join(tc.card_types)}")
    if tc.needs_pin is not None:
        parts.append(f"PIN Entry: {'Yes' if tc.needs_pin else 'No'}")
    if tc.is_standalone is not None:
        parts.append(f"Standalone: {'Yes' if tc.is_standalone else 'No/Unknown'}")
    if tc.power_source:
        parts.append(f"Power Source: {tc.power_source}")
    if tc.voltage:
        parts.append(f"Voltage: {tc.voltage}")
    if tc.host_interface:
        parts.append(f"Host Interface: {tc.host_interface}")
    if tc.standalone_comms:
        parts.append(f"Comms: {tc.standalone_comms}")
    if tc.needs_display is not None:
        parts.append(f"Needs Display: {'Yes' if tc.needs_display else 'No'}")
    if tc.previous_products:
        parts.append(f"Previous Products: {', '.join(tc.previous_products)}")
    if tp.monthly_volume is not None:
        parts.append(f"Monthly Volume: {tp.monthly_volume:,}")
    if tp.average_ticket is not None:
        parts.append(f"Avg Ticket: ${tp.average_ticket:.2f}")
    if lead.name:
        parts.append(f"Contact Name: {lead.name}")
    if lead.email:
        parts.append(f"Contact Email: {lead.email}")
    if lead.company:
        parts.append(f"Company: {lead.company}")
    if lead.phone:
        parts.append(f"Phone: {lead.phone}")

    if not parts:
        return "Nothing collected yet — you're starting fresh. Ask what they're working on."

    # Build a natural sentence highlighting what's known and what's still missing
    known_items = parts[:4]  # keep first few as bullet context
    summary = "\n".join(f"- {p}" for p in parts)

    # Add a note about what's still open
    gaps = []
    if not env.indoor_outdoor:
        gaps.append("indoor vs outdoor placement")
    if tc.card_types is None:
        gaps.append("which card types (contactless, chip, magstripe)")
    if tc.needs_pin is None:
        gaps.append("whether PIN entry is needed")
    if tc.is_standalone is None:
        gaps.append("standalone vs host-connected")
    if not lead.name:
        gaps.append("contact name")
    if not lead.email:
        gaps.append("contact email")

    if gaps:
        gap_text = ", ".join(gaps[:3])
        remaining = len(gaps) - 3
        if remaining > 0:
            gap_text += f", and {remaining} more details"
        summary += f"\nStill missing: {gap_text} — keep asking one thing at a time."

    return summary


def _build_valid_values_section() -> str:
    """Build a section listing valid use_case/category values from the knowledge files."""
    vmap = _load_vertical_map()
    mappings = vmap.get("mappings", {})

    use_cases = sorted(set(
        m.get("canonical", k) for k, m in mappings.items()
    ))

    lines = [
        "## Valid Use Case Values (use these exactly when calling search_products)",
    ]
    for uc in use_cases:
        lines.append(f"- {uc}")

    return "\n".join(lines)


def build_system_prompt(session: ConversationSession) -> str:
    """
    Build the complete system prompt for this turn based on the session state.

    Args:
        session: The current conversation session with all accumulated state.

    Returns:
        A formatted system prompt string for the LLM.
    """
    collected = session.collected_info

    # Determine stage
    stage = _determine_stage(collected, session.lead_submitted)

    known_summary = _build_known_summary(collected)

    products_summary = (
        ", ".join(session.recommended_products)
        if session.recommended_products
        else "None yet"
    )

    stage_instructions = STAGE_INSTRUCTIONS.get(stage, STAGE_INSTRUCTIONS["qualifying"])
    valid_values = _build_valid_values_section()

    return SYSTEM_PROMPT_TEMPLATE.format(
        stage=stage,
        stage_instructions=stage_instructions,
        known_summary=known_summary,
        recommended_products_summary=products_summary,
        valid_values_section=valid_values,
    )


def _determine_stage(collected: CollectedInfo, lead_submitted: bool) -> str:
    """Determine the current conversation stage based on collected info.

    Flow: greeting → qualifying → recommending → lead_capture → complete
    """
    if lead_submitted:
        return "complete"

    has_use_case = bool(collected.environment.vertical)
    has_environment = bool(collected.environment.indoor_outdoor)
    has_name = bool(collected.lead.name)
    has_email = bool(collected.lead.email)
    recommendation_shown = collected.meta.recommendation_shown

    # Check if we have enough technical context to make a recommendation
    tc = collected.technical_context
    has_tech = any([
        tc.card_types is not None,
        tc.needs_pin is not None,
        tc.is_standalone is not None,
        bool(tc.power_source),
        bool(tc.host_interface),
    ])

    if not has_use_case:
        return "greeting"

    if not (has_environment and has_tech):
        return "qualifying"

    # Have qualifying info but haven't shown recommendations yet
    if not recommendation_shown:
        return "recommending"

    # Recommendations shown, now check if we need lead info
    if not (has_name and has_email):
        return "lead_capture"

    return "complete"
