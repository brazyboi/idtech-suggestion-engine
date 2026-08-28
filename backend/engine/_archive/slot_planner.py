"""
Deterministic question planner for the conversational Q&A system.

Selects one canonical slot per turn from a fixed sequence, skipping already
answered slots.  The LLM only phrases the question — the backend remains the
source of truth for slot order, validation, and memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import typing
from typing import Any, Dict, List, Optional, Set

from .state_machine import CollectedInfo, ConversationState


class SlotParser(str, Enum):
    FREE_TEXT = "free_text"
    CHOICE = "choice"
    BOOLEAN = "boolean"
    NUMBER = "number"
    VOLUME_TICKET = "volume_ticket"


@dataclass
class SlotDef:
    """Definition of a single qualification slot the bot can ask about."""

    id: str
    path: str  # dotted path into CollectedInfo, e.g. "environment.indoor_outdoor"
    state: ConversationState
    prompt_hint: str  # one-sentence instruction to the LLM
    allowed_choices: List[str] = field(default_factory=list)
    fallback_choices: List[str] = field(default_factory=list)
    parser: SlotParser = SlotParser.FREE_TEXT
    max_attempts: int = 2
    accept_not_sure: bool = False
    required: bool = True

    # Conditional slots
    depends_on: Optional[str] = None  # slot id that must be ANSWERED first
    skip_if_path: Optional[str] = None  # dotted path — if set, skip this slot
    skip_if_value: Any = None  # skip when path == this value


# ── Canonical slot sequence ──────────────────────────────────────────────
SLOT_SEQUENCE: List[SlotDef] = [
    # ── GREETING ──
    SlotDef(
        id="vertical",
        path="environment.vertical",
        state=ConversationState.GREETING,
        prompt_hint="Ask what kind of business or industry they are in (parking, transit, vending, retail, EV charging, etc.).",
        allowed_choices=[
            "Parking / Transit",
            "Retail / POS",
            "Vending Machine",
            "EV Charging",
        ],
        fallback_choices=[
            "Parking / Transit",
            "Retail / POS",
            "Vending Machine",
            "EV Charging",
        ],
        parser=SlotParser.CHOICE,
    ),
    # ── QUALIFYING ──
    SlotDef(
        id="indoor_outdoor",
        path="environment.indoor_outdoor",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask whether the device will be installed indoors or outdoors.",
        allowed_choices=[
            "Indoor (0°C to 40°C)",
            "Outdoor (-20°C to 65°C)",
            "Outdoor harsh (-30°C to 70°C)",
        ],
        fallback_choices=[
            "Indoor (0°C to 40°C)",
            "Outdoor (-20°C to 65°C)",
            "Outdoor harsh (-30°C to 70°C)",
        ],
        parser=SlotParser.CHOICE,
    ),
    # ── QUALIFYING ──
    SlotDef(
        id="monthly_volume",
        path="transaction_profile.monthly_volume",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask approximately how many transactions they process per month.",
        allowed_choices=[
            "Under 1,000/month",
            "1,000 – 5,000/month",
            "5,000 – 20,000/month",
            "20,000+/month",
        ],
        fallback_choices=[
            "Under 1,000/month",
            "1,000 – 5,000/month",
            "5,000 – 20,000/month",
            "20,000+/month",
        ],
        parser=SlotParser.NUMBER,
        accept_not_sure=True,
    ),
    # ── QUALIFYING ──
    SlotDef(
        id="card_types",
        path="technical_context.card_types",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask which payment card types they need to accept (contact/chip, contactless/tap, magstripe/swipe). They may select multiple.",
        allowed_choices=[
            "Contact (chip)",
            "Contactless (tap)",
            "Magstripe (swipe)",
        ],
        fallback_choices=[
            "Contact (chip)",
            "Contactless (tap)",
            "Magstripe (swipe)",
        ],
        parser=SlotParser.CHOICE,
    ),
    SlotDef(
        id="needs_pin",
        path="technical_context.needs_pin",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask whether customers need to enter a PIN on the device.",
        allowed_choices=[
            "Yes, PIN required",
            "No PIN needed",
            "Not sure yet",
        ],
        fallback_choices=[
            "Yes, PIN required",
            "No PIN needed",
            "Not sure yet",
        ],
        parser=SlotParser.BOOLEAN,
        accept_not_sure=True,
    ),
    SlotDef(
        id="is_standalone",
        path="technical_context.is_standalone",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask whether the device runs standalone or connects to a host computer/terminal.",
        allowed_choices=[
            "Standalone (no host)",
            "Host-controlled",
            "Not sure yet",
        ],
        fallback_choices=[
            "Standalone (no host)",
            "Host-controlled",
            "Not sure yet",
        ],
        parser=SlotParser.BOOLEAN,
        accept_not_sure=True,
    ),
    SlotDef(
        id="power_source",
        path="technical_context.power_source",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask what power source is available (wall outlet, USB, battery).",
        allowed_choices=[
            "Wall outlet",
            "USB power",
            "Battery",
            "Not sure yet",
        ],
        fallback_choices=[
            "Wall outlet",
            "USB power",
            "Battery",
            "Not sure yet",
        ],
        parser=SlotParser.CHOICE,
        accept_not_sure=True,
    ),
    SlotDef(
        id="host_interface",
        path="technical_context.host_interface",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask which interface they need to connect to the host (USB, RS232, Ethernet, Bluetooth).",
        allowed_choices=[
            "USB",
            "RS232 / Serial",
            "Ethernet",
            "Bluetooth",
        ],
        fallback_choices=[
            "USB",
            "RS232 / Serial",
            "Ethernet",
            "Bluetooth",
        ],
        parser=SlotParser.CHOICE,
        depends_on="is_standalone",
        skip_if_path="technical_context.is_standalone",
        skip_if_value=True,  # skip if standalone
    ),
    SlotDef(
        id="standalone_comms",
        path="technical_context.standalone_comms",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask which communication method the standalone device should use (Ethernet, WiFi, Cellular).",
        allowed_choices=[
            "Ethernet",
            "WiFi",
            "Cellular (4G/5G)",
        ],
        fallback_choices=[
            "Ethernet",
            "WiFi",
            "Cellular (4G/5G)",
        ],
        parser=SlotParser.CHOICE,
        depends_on="is_standalone",
        skip_if_path="technical_context.is_standalone",
        skip_if_value=False,  # skip if host-controlled
    ),
    SlotDef(
        id="needs_display",
        path="technical_context.needs_display",
        state=ConversationState.QUALIFYING,
        prompt_hint="Ask whether they need a display/screen on the device for customer interaction.",
        allowed_choices=[
            "Yes, display needed",
            "No display needed",
            "Not sure yet",
        ],
        fallback_choices=[
            "Yes, display needed",
            "No display needed",
            "Not sure yet",
        ],
        parser=SlotParser.BOOLEAN,
        accept_not_sure=True,
    ),
    # ── LEAD CAPTURE ──
    SlotDef(
        id="lead_name",
        path="lead.name",
        state=ConversationState.LEAD_CAPTURE,
        prompt_hint="Ask for their name so a specialist can follow up.",
        parser=SlotParser.FREE_TEXT,
    ),
    SlotDef(
        id="lead_email",
        path="lead.email",
        state=ConversationState.LEAD_CAPTURE,
        prompt_hint="Ask for their email address so we can send the recommendation and follow up.",
        parser=SlotParser.FREE_TEXT,
    ),
]

# Lookup helper
SLOT_BY_ID: Dict[str, SlotDef] = {s.id: s for s in SLOT_SEQUENCE}


def _get_nested(obj: Any, dotted_path: str) -> Any:
    """Get a nested value from CollectedInfo or dict by dotted path."""
    parts = dotted_path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
        if current is None:
            return None
    return current


def _set_nested(obj: Any, dotted_path: str, value: Any) -> None:
    """Set a nested value on a dict by dotted path."""
    parts = dotted_path.split(".")
    current = obj
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _is_slot_answered(slot: SlotDef, collected: CollectedInfo) -> bool:
    """Check whether the slot's target path already has a value."""
    val = _get_nested(collected, slot.path)
    if val is None:
        return False
    if isinstance(val, list) and len(val) == 0:
        return False
    if isinstance(val, str) and val.strip() == "":
        return False
    return True


def _should_skip_slot(slot: SlotDef, collected: CollectedInfo) -> bool:
    """Check conditional skip rules for a slot."""
    if slot.skip_if_path:
        val = _get_nested(collected, slot.skip_if_path)
        if val is not None and val == slot.skip_if_value:
            return True
    if slot.depends_on:
        dep_slot = SLOT_BY_ID.get(slot.depends_on)
        if dep_slot and not _is_slot_answered(dep_slot, collected):
            return True
    return False


def normalize_choice(slot_id: str, raw_value: Any) -> Any:
    """
    Map raw LLM output to canonical choice value(s) for the given slot.

    Pure function — no LLM dependency, no side effects, fully testable.

    Handles:
    - Exact matches (case-insensitive)
    - "all of them" / "everything" → all allowed choices
    - Comma-separated partial matches ("chip, tap")
    - Substring / token overlap fuzzy match
    - Fall through: return raw_value unchanged

    Returns a list for multi-select fields (card_types, previous_products),
    a scalar string for single-select fields.
    """
    slot = SLOT_BY_ID.get(slot_id)
    if not slot or not slot.allowed_choices:
        return raw_value

    # Normalize to string
    if isinstance(raw_value, list):
        raw_value = ", ".join(raw_value)
    if not isinstance(raw_value, str):
        return raw_value

    choices = slot.allowed_choices
    cleaned = raw_value.strip()
    lowered = cleaned.lower()

    # "all of them" / "everything" — only valid for multi-select fields
    # For single-select fields (e.g. indoor_outdoor), "all of them" is ambiguous
    # and would silently pick the first choice. Fall through to raw value instead.
    _all_phrases = {"all", "all of them", "everything", "every option",
                    "all types", "all three", "all the above", "all available",
                    "yes all", "both", "accept all"}
    if lowered in _all_phrases:
        if _is_field_list(slot):
            return _as_slot_type(slot, list(choices))
        # Single-select — "all of them" is ambiguous, fall through to raw value
        return raw_value

    # Exact case-insensitive match against single choice
    for c in choices:
        if c.lower() == lowered:
            return _as_slot_type(slot, [c])

    # Comma-separated tokens: "chip, tap" → match each token to a choice
    tokens = [t.strip() for t in cleaned.split(",")]
    matched: List[str] = []
    for token in tokens:
        if not token:
            continue
        token_lower = token.lower()
        found = False
        # Exact token match
        for c in choices:
            if c.lower() == token_lower:
                matched.append(c)
                found = True
                break
        if found:
            continue
        # Substring / token overlap: "chip" in "Contact (chip)"
        for c in choices:
            c_lower = c.lower()
            if token_lower in c_lower or c_lower in token_lower:
                matched.append(c)
                found = True
                break
        if found:
            continue

    if matched:
        # Deduplicate preserving order
        seen: Set[str] = set()
        result = []
        for c in matched:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return _as_slot_type(slot, result)

    # Single fuzzy substring match against whole input
    for c in choices:
        if lowered in c.lower() or c.lower() in lowered:
            return _as_slot_type(slot, [c])

    # Fall through: return raw string unchanged (backend keeps it)
    return raw_value


def _as_slot_type(slot: SlotDef, matched: List[str]) -> Any:
    """Return a list for multi-select fields, a scalar string otherwise."""
    if _is_field_list(slot):
        return matched  # List[str]
    return matched[0] if matched else ""


def _is_field_list(slot: SlotDef) -> bool:
    """Check whether the field behind a slot is typed as List[str]."""
    parts = slot.path.split(".")
    if len(parts) != 2:
        return False
    section_name, field_name = parts
    # Walk the CollectedInfo model to find the field annotation
    section_info = CollectedInfo.model_fields.get(section_name)
    if section_info is None:
        return False
    section_annotation = section_info.annotation
    if section_annotation is None:
        return False
    # Unwrap Optional[X] → X
    origin = typing.get_origin(section_annotation)
    if origin is typing.Union:
        args = typing.get_args(section_annotation)
        section_annotation = next((a for a in args if a is not type(None)), section_annotation)
    if not hasattr(section_annotation, "model_fields"):
        return False
    field_info = section_annotation.model_fields.get(field_name)
    if field_info is None:
        return False
    field_annotation = field_info.annotation
    if field_annotation is None:
        return False
    origin = typing.get_origin(field_annotation)
    if origin is typing.Union:
        args = typing.get_args(field_annotation)
        field_annotation = next((a for a in args if a is not type(None)), field_annotation)
    return typing.get_origin(field_annotation) is list


class SlotPlanner:
    """
    Deterministic question planner.

    Tracks which slots have been asked / answered and selects the next
    unanswered slot from the canonical sequence.
    """

    @staticmethod
    def select_next_slot(
        collected: CollectedInfo,
        asked_slots: Set[str],
        answered_slots: Set[str],
        slot_attempts: Dict[str, int],
    ) -> Optional[SlotDef]:
        """
        Pick the first slot in the sequence that:
        - Is not already answered
        - Has not exceeded max_attempts (unless it was answered with "not sure")
        - Has its dependencies satisfied
        - Is not conditionally skipped
        """
        for slot in SLOT_SEQUENCE:
            # Already answered — skip
            if slot.id in answered_slots:
                continue

            # Conditional skip
            if _should_skip_slot(slot, collected):
                # Mark as answered so planner doesn't get stuck
                continue

            # Retry cap
            attempts = slot_attempts.get(slot.id, 0)
            if attempts >= slot.max_attempts:
                # Mark as answered at cap so we don't loop forever
                continue

            # Dependency check
            if slot.depends_on:
                dep_slot = SLOT_BY_ID.get(slot.depends_on)
                if dep_slot and dep_slot.id not in answered_slots:
                    # Dependency not yet answered — skip for now
                    continue

            return slot

        return None

    @staticmethod
    def record_asked(slot_id: str, asked_slots: Set[str], slot_attempts: Dict[str, int]) -> None:
        """Mark a slot as asked and increment attempt counter."""
        asked_slots.add(slot_id)
        slot_attempts[slot_id] = slot_attempts.get(slot_id, 0) + 1

    @staticmethod
    def record_answered(slot_id: str, answered_slots: Set[str]) -> None:
        """Mark a slot as successfully answered."""
        answered_slots.add(slot_id)

    @staticmethod
    def all_required_answered(
        collected: CollectedInfo,
        answered_slots: Set[str],
        up_to_state: ConversationState,
    ) -> bool:
        """Check if all required slots up to (and including) the given state are answered."""
        for slot in SLOT_SEQUENCE:
            if _should_skip_slot(slot, collected):
                continue
            if not slot.required:
                continue
            if slot.state not in _states_up_to(up_to_state):
                continue
            if slot.id not in answered_slots:
                # Also check if the path itself has a value (e.g. parsed)
                if _is_slot_answered(slot, collected):
                    continue
                return False
        return True


def _states_up_to(state: ConversationState) -> Set[ConversationState]:
    """Return all states up to and including the given state in the conversation flow."""
    order = [
        ConversationState.GREETING,
        ConversationState.QUALIFYING,
        ConversationState.RECOMMENDING,
        ConversationState.LEAD_CAPTURE,
        ConversationState.HANDOFF,
    ]
    result: Set[ConversationState] = set()
    for s in order:
        result.add(s)
        if s == state:
            break
    return result


def get_slot_choice_vocab(slot_id: str) -> List[str]:
    """Return the canonical allowed choices for a slot (lowercased, for validation)."""
    slot = SLOT_BY_ID.get(slot_id)
    if not slot:
        return []
    return [c.lower().strip() for c in slot.allowed_choices]


def validate_choices_for_slot(slot_id: str, choices: List[str]) -> bool:
    """
    Validate that the LLM-provided choices are aligned with the planned slot.
    Returns True if at least one choice token overlaps with the canonical vocab.
    """
    if not choices:
        return False
    vocab = get_slot_choice_vocab(slot_id)
    if not vocab:
        # Free-text slots should not have suggested choices.
        return False
    joined_choices = " ".join(c.lower() for c in choices)
    # At least one canonical token should appear in the choices
    for token in vocab:
        # Check if the token (or a significant part) appears in the choices
        if len(token) > 3 and token in joined_choices:
            return True
        for word in token.split():
            if len(word) > 3 and word in joined_choices:
                return True
    return False
