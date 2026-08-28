"""
Enforces the ASK_SLOT contract between the LLM and the slot planner.

When a slot is planned, the LLM MUST produce a valid question about that slot.
If it doesn't (e.g., it changes the subject, or produces a closing remark),
this service falls back to a canned question.

Quick-reply buttons are ONLY provided when the LLM voluntarily calls the
`present_choices` tool. No static fallback choices are injected — if the
LLM didn't think buttons were appropriate, they won't appear.
"""

from typing import List, Tuple

from ..engine.slot_planner import SlotDef


class SlotContractEnforcer:
    """
    Validates the LLM's output against the slot contract and provides
    fallback questions/choices when the LLM fails.
    """

    # Phrases that indicate the LLM is trying to end the conversation
    CLOSING_MARKERS = [
        "feel free to ask",
        "let me know if you have any more questions",
        "if you have any more questions",
        "anything else i can help",
        "anything else you want to discuss",
        "happy to help",
    ]

    @staticmethod
    def _has_closing_markers(text: str) -> bool:
        """Check if the text contains conversation-ending phrases."""
        lowered = text.lower()
        return any(marker in lowered for marker in SlotContractEnforcer.CLOSING_MARKERS)

    @staticmethod
    def is_valid_question_reply(text: str) -> bool:
        """Check if the LLM reply is a valid single-question message."""
        if not text or not text.strip():
            return False
        if SlotContractEnforcer._has_closing_markers(text):
            return False
        if text.count("?") != 1:
            return False
        return text.strip().endswith("?")

    @staticmethod
    def fallback_question_for_slot(slot: SlotDef) -> str:
        """Return a deterministic canned question for a given slot."""
        by_slot = {
            "vertical": "What industry or use case are you working on?",
            "indoor_outdoor": "Will your deployment be indoors or outdoors?",
            "monthly_volume": "About how many transactions do you expect per month?",
            "card_types": "Which card types do you need to accept: contact/chip, contactless/tap, or magstripe/swipe?",
            "needs_pin": "Do customers need to enter a PIN on the device?",
            "is_standalone": "Will this be a standalone device, or host-controlled?",
            "power_source": "What power source is available: wall outlet, USB power, or battery?",
            "host_interface": "Which host interface do you need: USB, RS232/Serial, Ethernet, or Bluetooth?",
            "standalone_comms": "For standalone deployment, which communication method do you need: Ethernet, WiFi, or Cellular?",
            "needs_display": "Do you need a display on the device?",
            "lead_name": "Could I get your name so we can follow up with the right specialist?",
            "lead_email": "Could you share the best email address for follow-up?",
        }
        return by_slot.get(slot.id, "Could you share a bit more detail?")

    @staticmethod
    def _next_slot_question(slot_id: str) -> str:
        """Return just the canned question for the next slot (no prefix)."""
        by_slot = {
            "vertical": "What industry or use case are you working on?",
            "indoor_outdoor": "Will your deployment be indoors or outdoors?",
            "monthly_volume": "About how many transactions do you expect per month?",
            "card_types": "Which card types do you need to accept: contact/chip, contactless/tap, or magstripe/swipe?",
            "needs_pin": "Do customers need to enter a PIN on the device?",
            "is_standalone": "Will this be a standalone device, or host-controlled?",
            "power_source": "What power source is available: wall outlet, USB power, or battery?",
            "host_interface": "Which host interface do you need: USB, RS232/Serial, Ethernet, or Bluetooth?",
            "standalone_comms": "For standalone deployment, which communication method do you need: Ethernet, WiFi, or Cellular?",
            "needs_display": "Do you need a display on the device?",
            "lead_name": "Could I get your name so we can follow up with the right specialist?",
            "lead_email": "Could you share the best email address for follow-up?",
        }
        return by_slot.get(slot_id, "")

    @staticmethod
    def enforce(
        slot: SlotDef,
        reply: str,
        suggested_choices: List[str],
        choice_validation: str,
        slot_just_answered: bool = False,
        next_slot_id: str | None = None,
    ) -> Tuple[str, List[str], str]:
        """
        Enforce the ASK_SLOT contract.

        When slot_just_answered is True, the slot was successfully extracted
        this turn — do NOT override the LLM's reply with a canned question.

        When a next_slot_id is provided (slot was answered and a follow-up
        question is expected), the fallback "Got it, thanks!" is replaced with
        a contextual transition like "Got it! Will your deployment be indoors
        or outdoors?"

        Returns:
            (final_reply, final_choices, final_validation)
        """
        final_reply = reply
        final_choices: List[str] = []
        final_validation = choice_validation

        if slot_just_answered:
            # Extraction succeeded — the LLM's job is done this turn.
            #
            # Strategy (in order of preference):
            # 1. If the LLM already asked a question ("?" in reply), KEEP it.
            #    The prompt now tells the LLM the next topic, so its question
            #    is probably about the right thing — no need to override.
            # 2. If the LLM gave a clean acknowledgment (no "?"), and we know
            #    the next slot, APPEND the next question naturally.
            # 3. If the reply is empty or has closing markers, REPLACE with
            #    a canned transition or "Got it, thanks!" as last resort.
            #
            # Choices: only provided when the LLM called present_choices.
            # No static fallback — if the LLM didn't think buttons made sense,
            # injecting them would confuse the user.
            has_q = "?" in final_reply
            has_closing = SlotContractEnforcer._has_closing_markers(final_reply)

            if suggested_choices and choice_validation == "valid":
                choices = list(suggested_choices)[:4]
            else:
                choices = []

            if has_q:
                # LLM asked a question — keep it (likely the right next topic).
                final_choices = choices
            elif has_closing or not final_reply.strip():
                # Bad reply — use canned transition or generic
                if next_slot_id:
                    q = SlotContractEnforcer._next_slot_question(next_slot_id)
                    if q:
                        final_reply = f"Got it! {q}"
                        final_choices = choices
                    else:
                        final_reply = "Got it, thanks!"
                else:
                    final_reply = "Got it, thanks!"
            else:
                # Clean acknowledgment with no question — append next question
                if next_slot_id:
                    q = SlotContractEnforcer._next_slot_question(next_slot_id)
                    if q:
                        final_reply = f"{final_reply.strip()} {q}"
                        final_choices = choices
                # else: no next slot, keep the clean ack

            return final_reply, final_choices, final_validation

        if not SlotContractEnforcer.is_valid_question_reply(final_reply):
            final_reply = SlotContractEnforcer.fallback_question_for_slot(slot)
            final_validation = "contract_reply_fallback"

        # Choices: only from LLM's present_choices. No static fallback.
        if suggested_choices and choice_validation == "valid":
            final_choices = list(suggested_choices)[:4]
        return final_reply, final_choices, final_validation
