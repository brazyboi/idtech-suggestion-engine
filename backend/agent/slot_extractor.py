"""
Slot extractor — passively extracts qualification and lead info from user messages.

Uses gpt-4o-mini for lightweight extraction of:
- Industry/vertical (use case)
- Environment (indoor/outdoor, temperature)
- Technical context (card types, PIN, standalone, power, interface)
- Transaction profile (monthly volume, average ticket)
- Lead info (name, email, company, phone)

Extracts flat fields from the LLM and maps them into CollectedInfo's nested structure.
Runs silently after every user message — does NOT produce assistant text.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

from ..engine.state_machine import CollectedInfo

load_dotenv()
logger = logging.getLogger(__name__)


EXTRACTOR_SYSTEM_PROMPT = """
You are an information extractor for a B2B payment hardware sales conversation.

Given the user's latest message, extract any of the following fields if the user MENTIONS them.
Return ONLY a JSON object with the fields you find. Omit fields that are not mentioned at all.
Do not guess or infer — only extract what is explicitly stated or very clearly implied.

Fields (all optional — only include what's mentioned):

Industry / Use Case:
- vertical: what kind of business or industry (e.g., "parking", "transit", "retail", "vending", "EV charging", "hospitality", "healthcare", "car wash", "fueling")

Environment:
- indoor_outdoor: "indoor", "outdoor", or "indoor and outdoor"
- temperature_range: any temperature information mentioned

Technical Context:
- card_types: array of card types — "contact"/"chip", "contactless"/"tap"/"NFC", "magstripe"/"swipe"
- needs_pin: boolean — whether they need PIN entry on the device
- is_standalone: boolean — whether they need a standalone device (no host computer)
- power_source: power source — "USB", "wall outlet"/"VAC", "battery", "PoE"
- voltage: specific voltage if mentioned
- host_interface: interface to host — "USB", "RS232"/"Serial", "Ethernet", "Bluetooth"
- standalone_comms: communication method for standalone — "Ethernet", "WiFi", "Cellular"/"4G"/"LTE"
- needs_display: boolean — whether they need a screen/display
- previous_products: array of product names or brands they've used before

Transaction Profile:
- monthly_volume: number of transactions per month (as integer)
- average_ticket: average transaction value in dollars (as number)

Lead Info:
- name: person's first and/or last name
- email: email address
- company: company or organization name
- phone: phone number

Example output:
{"vertical": "parking", "indoor_outdoor": "outdoor", "card_types": ["contactless"]}
""".strip()


class SlotExtractor:
    """
    Lightweight extractor that runs after every user message.

    Extracts flat fields and maps them into CollectedInfo's nested structure.
    Does NOT overwrite already-collected fields — only fills in gaps.
    """

    # Flat field → CollectedInfo path mapping
    FIELD_MAP: Dict[str, str] = {
        # environment.*
        "vertical": "environment.vertical",
        "indoor_outdoor": "environment.indoor_outdoor",
        "temperature_range": "environment.temperature_range",
        # technical_context.*
        "card_types": "technical_context.card_types",
        "needs_pin": "technical_context.needs_pin",
        "is_standalone": "technical_context.is_standalone",
        "power_source": "technical_context.power_source",
        "voltage": "technical_context.voltage",
        "host_interface": "technical_context.host_interface",
        "standalone_comms": "technical_context.standalone_comms",
        "needs_display": "technical_context.needs_display",
        "previous_products": "technical_context.previous_products",
        # transaction_profile.*
        "monthly_volume": "transaction_profile.monthly_volume",
        "average_ticket": "transaction_profile.average_ticket",
        # lead.*
        "name": "lead.name",
        "email": "lead.email",
        "company": "lead.company",
        "phone": "lead.phone",
    }

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY")
        self.client = OpenAI(api_key=api_key or "test-key")
        self.model = "gpt-4o-mini"

    def extract(self, user_message: str, collected: CollectedInfo) -> Dict[str, Any]:
        """
        Extract fields from the user message and merge into CollectedInfo.

        Args:
            user_message: The user's latest message.
            collected: The current CollectedInfo (mutated in-place).

        Returns:
            A dict of what was newly extracted (flat field → value).
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=300,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": EXTRACTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            raw = response.choices[0].message.content or "{}"
            extracted: Dict[str, Any] = json.loads(raw)

        except Exception as e:
            logger.debug("Slot extraction failed: %s", e)
            return {}

        # Merge into CollectedInfo — only set fields that are not already known
        new_info: Dict[str, Any] = {}
        for flat_field, value in extracted.items():
            if value is None:
                continue
            if flat_field not in self.FIELD_MAP:
                continue

            path = self.FIELD_MAP[flat_field]
            section_name, sub_field = path.split(".", 1)

            section = getattr(collected, section_name, None)
            if section is None:
                continue

            current_value = getattr(section, sub_field, None)
            if current_value is not None:
                # Already collected — don't overwrite
                continue

            # Clean boolean-like strings
            if isinstance(value, str):
                lower = value.lower().strip()
                if lower in ("yes", "true", "y", "1"):
                    value = True
                elif lower in ("no", "false", "n", "0"):
                    value = False

            # Clean int-like values
            if isinstance(value, str) and value.isdigit():
                value = int(value)

            setattr(section, sub_field, value)
            new_info[flat_field] = value

        return new_info


# Singleton
_extractor = SlotExtractor()


def extract_slots(user_message: str, collected: CollectedInfo) -> Dict[str, Any]:
    """
    Convenience wrapper — extracts slots and merges into CollectedInfo.

    Returns dict of newly extracted fields.
    """
    return _extractor.extract(user_message, collected)
