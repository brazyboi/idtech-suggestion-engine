"""
Normalizes extracted info from the LLM back into the CollectedInfo structure.

The LLM can place fields in slightly wrong sections or use non-standard names.
This service maps those back to the canonical schema and silently drops
unknown fields.
"""

from typing import Any, Dict, Set

from ..engine.slot_planner import SLOT_BY_ID, _is_slot_answered
from ..engine.state_machine import CollectedInfo


class InfoNormalizer:
    """
    Normalizes LLM-extracted data into the canonical CollectedInfo schema.

    Responsibilities:
    - Map known fields from raw extraction dict into proper sections
    - Silently drop unknown fields (no crashes from LLM hallunications)
    - Sync slot tracker when new info arrives
    """

    # Canonical set of allowed fields per section
    KNOWN_FIELDS: Dict[str, Set[str]] = {
        "environment": {"vertical", "indoor_outdoor", "temperature_range"},
        "transaction_profile": {"monthly_volume", "average_ticket"},
        "technical_context": {
            "power_source", "voltage", "card_types", "needs_pin",
            "is_standalone", "host_interface", "host_os",
            "standalone_comms", "needs_display", "previous_products",
        },
        "lead": {"name", "email", "company", "phone"},
        "meta": {"recommendation_shown"},
    }

    KNOWN_SECTIONS = {"environment", "transaction_profile", "technical_context", "lead", "meta"}

    @staticmethod
    def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Take a raw extraction dict (from the LLM tool call) and return a
        cleaned dict with only known fields in their proper sections.

        Args:
            raw: The raw extracted_info dict from the LLM.

        Returns:
            A cleaned dict suitable for merging into CollectedInfo.
        """
        if not raw:
            return {}

        cleaned: Dict[str, Any] = {}

        for key, value in raw.items():
            if key in InfoNormalizer.KNOWN_SECTIONS:
                if isinstance(value, dict):
                    cleaned[key] = InfoNormalizer._clean_section(key, value)
            elif key == "__state_override":
                cleaned[key] = value
            # Unknown top-level keys are silently ignored

        return cleaned

    @staticmethod
    def _clean_section(section: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean a section dict, keeping only known fields. Normalizes
        CHOICE slot values to canonical form."""
        allowed = InfoNormalizer.KNOWN_FIELDS.get(section, set())
        result: Dict[str, Any] = {}
        for k, v in data.items():
            if k in allowed:
                result[k] = InfoNormalizer._normalize_field_value(section, k, v)
            # else: silently ignore unknown field
        return result

    @staticmethod
    def _normalize_field_value(section: str, field: str, value: Any) -> Any:
        """If a CHOICE slot maps to this section.field, canonicalize the value."""
        from ..engine.slot_planner import SLOT_BY_ID, normalize_choice
        dotted = f"{section}.{field}"
        for slot_id, slot_def in SLOT_BY_ID.items():
            if slot_def.path == dotted and slot_def.allowed_choices:
                return normalize_choice(slot_id, value)
        return value

    @staticmethod
    def sync_answered_slots(
        collected: CollectedInfo,
        answered_slots: Set[str],
    ) -> None:
        """
        Scan all slot definitions and mark any that now have a value in
        collected info as answered.
        """
        for slot in SLOT_BY_ID.values():
            if _is_slot_answered(slot, collected):
                answered_slots.add(slot.id)
