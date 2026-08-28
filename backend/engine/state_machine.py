from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


class ConversationState(str, Enum):
    GREETING = "greeting"
    QUALIFYING = "qualifying"
    RECOMMENDING = "recommending"
    LEAD_CAPTURE = "lead_capture"
    HANDOFF = "handoff"


class EnvironmentInfo(BaseModel):
    vertical: Optional[str] = None
    indoor_outdoor: Optional[str] = None
    temperature_range: Optional[str] = None


class TransactionProfile(BaseModel):
    monthly_volume: Optional[int] = None
    average_ticket: Optional[float] = None


class TechnicalContext(BaseModel):
    power_source: Optional[str] = None
    voltage: Optional[str] = None
    card_types: Optional[List[str]] = None
    needs_pin: Optional[bool] = None
    is_standalone: Optional[bool] = None
    host_interface: Optional[str] = None
    host_os: Optional[str] = None
    standalone_comms: Optional[str] = None
    needs_display: Optional[bool] = None
    previous_products: Optional[List[str]] = None


class LeadInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None


class ConversationMeta(BaseModel):
    recommendation_shown: bool = False


class CollectedInfo(BaseModel):
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)
    transaction_profile: TransactionProfile = Field(default_factory=TransactionProfile)
    technical_context: TechnicalContext = Field(default_factory=TechnicalContext)
    lead: LeadInfo = Field(default_factory=LeadInfo)
    meta: ConversationMeta = Field(default_factory=ConversationMeta)

    def merge(self, update: Dict[str, Any]) -> "CollectedInfo":
        for key, value in update.items():
            if key in ("environment", "transaction_profile", "technical_context", "lead", "meta"):
                sub = getattr(self, key)
                if isinstance(value, dict):
                    for sub_key, sub_val in value.items():
                        if sub_val is not None and hasattr(sub, sub_key):
                            setattr(sub, sub_key, sub_val)
                elif value is not None:
                    setattr(self, key, value)
            else:
                if value is not None and hasattr(self, key):
                    setattr(self, key, value)
        return self

    def to_flat_constraints(self) -> Dict[str, Any]:
        tc = self.technical_context
        env = self.environment
        constraints: Dict[str, Any] = {}

        if env.vertical:
            constraints["use_case"] = _normalize_use_case(env.vertical)
        if env.indoor_outdoor in ("outdoor", "outdoor harsh"):
            constraints["is_outdoor"] = True
        if env.temperature_range:
            import re
            match = re.search(r"(-?\d+)", env.temperature_range)
            if match:
                constraints["operate_temperature"] = match.group(1)

        if tc.voltage:
            constraints["input_power"] = tc.voltage
        if tc.power_source:
            lower = tc.power_source.lower()
            if "usb" in lower:
                constraints["input_power"] = "USB"
            elif "wall" in lower or "outlet" in lower:
                constraints["input_power"] = "VAC"
        if tc.host_interface:
            constraints["interface"] = tc.host_interface
        if tc.standalone_comms:
            constraints["interface"] = tc.standalone_comms
        if tc.is_standalone:
            constraints["is_standalone"] = True

        extra_tags: List[str] = []
        if tc.needs_pin:
            extra_tags.append("PIN")
        if tc.card_types and "contactless" in tc.card_types:
            extra_tags.append("contactless")
        if extra_tags:
            constraints["extra_specs_filter"] = ",".join(extra_tags)

        if tc.previous_products:
            constraints["search_query"] = tc.previous_products[0]

        return constraints


class ConversationSession(BaseModel):
    """
    Single source of truth for all conversation state.

    Replaces the previous pattern of passing 5 separate dicts/sets
    (history, collected_info, asked_slots, answered_slots, slot_attempts)
    through the pipeline. Now everything lives in one model.

    Fields added for agentic loop:
    - intent: the classified intent for the current turn
    - turn_count: how many user turns have occurred
    - recommended_products: list of product model names shown to the user
    - lead_submitted: guard against duplicate lead submissions
    - reasoning_trace: step-by-step agent decision log per turn
    """

    id: str = ""
    history: List[Dict[str, str]] = Field(default_factory=list)
    collected_info: CollectedInfo = Field(default_factory=CollectedInfo)
    asked_slots: Set[str] = Field(default_factory=set)
    answered_slots: Set[str] = Field(default_factory=set)
    slot_attempts: Dict[str, int] = Field(default_factory=dict)
    last_planned_slot: Optional[str] = None

    # ── Agentic loop fields ──
    intent: Optional[str] = None
    turn_count: int = 0
    recommended_products: List[str] = Field(default_factory=list)
    lead_submitted: bool = False
    reasoning_trace: List[Dict[str, Any]] = Field(default_factory=list)


def _normalize_use_case(value: str) -> str:
    lower = value.lower().strip()
    mapping = {
        "parking": "Parking Payment Systems",
        "parking / transit": "Parking Payment Systems",
        "transit": "Transit Payment Solutions",
        "retail": "Loyalty Program Contactless Readers",
        "retail / pos": "Loyalty Program Contactless Readers",
        "vending": "Vending Payment Systems",
        "vending machine": "Vending Payment Systems",
        "ev charging": "EV Charging Station Payment Solutions",
    }
    for token, canonical in mapping.items():
        if token in lower:
            return canonical
    return value


def _is_technical_context_ready(collected: CollectedInfo) -> bool:
    tc = collected.technical_context
    primary_signals = [
        tc.card_types is not None,
        tc.needs_pin is not None,
        tc.is_standalone is not None,
    ]
    if sum(primary_signals) >= 2:
        return True

    secondary_signals = [
        bool(tc.power_source),
        bool(tc.voltage),
        bool(tc.host_interface),
        bool(tc.standalone_comms),
        tc.needs_display is not None,
    ]
    return sum(secondary_signals) >= 2


def state_order(state: ConversationState) -> int:
    order = [
        ConversationState.GREETING,
        ConversationState.QUALIFYING,
        ConversationState.RECOMMENDING,
        ConversationState.LEAD_CAPTURE,
        ConversationState.HANDOFF,
    ]
    return order.index(state)


def determine_next_state(collected: CollectedInfo) -> ConversationState:
    has_use_case = bool(collected.environment.vertical)
    has_environment = bool(collected.environment.indoor_outdoor)
    has_name = bool(collected.lead.name)
    has_email = bool(collected.lead.email)

    if not has_use_case:
        return ConversationState.GREETING
    if not has_environment or not _is_technical_context_ready(collected):
        return ConversationState.QUALIFYING
    if not collected.meta.recommendation_shown:
        return ConversationState.RECOMMENDING
    if not (has_name and has_email):
        return ConversationState.LEAD_CAPTURE
    return ConversationState.HANDOFF