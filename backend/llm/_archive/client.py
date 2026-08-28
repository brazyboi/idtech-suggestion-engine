from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .prompts import build_tools_for_planned_slot, build_chat_prompt

# Lazy import to avoid circular dependency at module level
_slot_planner = None

def _get_slot_planner():
    global _slot_planner
    if _slot_planner is None:
        from ..engine.slot_planner import validate_choices_for_slot, get_slot_choice_vocab
        _slot_planner = type("_", (), {
            "validate_choices_for_slot": staticmethod(validate_choices_for_slot),
            "get_slot_choice_vocab": staticmethod(get_slot_choice_vocab),
        })
    return _slot_planner


load_dotenv()
logger = logging.getLogger(__name__)


class LLMClient:
    """
    Thin wrapper around OpenAI. Responsibilities:
    - Call the LLM with per-state prompt + tools
    - Parse tool call arguments (update_lead_info, present_choices)
    - Return the extracted data + assistant text reply + suggested choices
    - DOES NOT contain product logic, state machine, or recommendation building
    """

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY")
        if not api_key:
            api_key = "test-key"
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"
        self.max_attempts = 3

    @staticmethod
    def _deep_merge_dict(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        """Deep-merge nested tool payloads so multiple calls in one turn don't clobber fields."""
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                LLMClient._deep_merge_dict(base[key], value)
            else:
                base[key] = value
        return base

    def process_turn(
        self,
        message: str,
        history: List[Dict[str, str]],
        state: str = "greeting",
        collected_info: Optional[Dict[str, Any]] = None,
        planned_slot_id: Optional[str] = None,
        slot_prompt_hint: Optional[str] = None,
        next_topic_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a turn to the LLM and return:
        {
            "reply": str,                # The assistant's text response
            "extracted_info": dict,      # Data extracted via update_lead_info tool call
            "suggested_choices": list,   # Choices from present_choices tool call
            "tool_was_called": bool,     # Whether any tool was invoked
            "accepted_slot": str | None, # Slot from present_choices if validated
            "choice_validation": str,    # "valid" | "rejected_mismatch" | "rejected_vocab" | "fallback"
        }
        """
        # Build per-slot tools (constrained to the current planned slot only)
        tools = build_tools_for_planned_slot(planned_slot_id)

        messages: List[Dict[str, Any]] = build_chat_prompt(
            message, history, state, collected_info,
            planned_slot_id=planned_slot_id,
            slot_prompt_hint=slot_prompt_hint,
            next_topic_hint=next_topic_hint,
        )

        extracted_info: Dict[str, Any] = {}
        suggested_choices: List[str] = []
        tool_was_called = False
        accepted_slot: Optional[str] = None
        choice_validation: str = "none"
        must_generate_text = False  # becomes True once tools have been processed

        for attempt in range(1, self.max_attempts + 1):
            # After tools have been processed once, force the LLM to produce
            # conversational text — no further tool calls allowed this turn.
            # On retry (attempt > 1), force the specific extraction tool.
            if must_generate_text:
                effective_tool_choice: Any = "none"
            elif attempt > 1 and planned_slot_id:
                effective_tool_choice = {
                    "type": "function",
                    "function": {"name": f"extract_{planned_slot_id}"},
                }
            elif attempt > 1:
                effective_tool_choice = "required"
            else:
                effective_tool_choice = "auto"

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice=effective_tool_choice,
                )
            except Exception as exc:
                logger.error("OpenAI API call failed (attempt %d/%d): %s", attempt, self.max_attempts, exc)
                if attempt < self.max_attempts:
                    continue
                return {
                    "reply": "Sorry, I'm having trouble connecting right now. Could you try again?",
                    "extracted_info": extracted_info,
                    "suggested_choices": suggested_choices,
                    "tool_was_called": tool_was_called,
                    "accepted_slot": accepted_slot,
                    "choice_validation": choice_validation,
                }

            response_message = response.choices[0].message
            reply_text = response_message.content or ""

            # Append the assistant message (with tool_calls if any) to the conversation
            msg_dict: Dict[str, Any] = {
                "role": response_message.role,
                "content": reply_text,
            }
            if response_message.tool_calls:
                msg_dict["tool_calls"] = [tc.model_dump() for tc in response_message.tool_calls]
            messages.append(msg_dict)

            tool_calls = response_message.tool_calls or []

            # ── No tool calls → retry with hint if attempts remain ──
            if not tool_calls:
                if attempt < self.max_attempts:
                    # The LLM responded with text but didn't call any tools.
                    # Give it another chance with a stronger hint.
                    messages.append({
                        "role": "system",
                        "content": (
                            "You MUST call the available extraction tool if the user "
                            "provided any information relevant to the planned topic. "
                            "Do not just respond with text \u2014 capture the data first."
                        ),
                    })
                    continue
                return {
                    "reply": reply_text,
                    "extracted_info": extracted_info,
                    "suggested_choices": suggested_choices,
                    "tool_was_called": tool_was_called,
                    "accepted_slot": accepted_slot,
                    "choice_validation": choice_validation,
                }

            # ── Process tool calls ──
            any_unknown = False
            for tool_call in tool_calls:
                fname = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else {}
                except json.JSONDecodeError:
                    args = {}

                if fname.startswith("extract_"):
                    if isinstance(args, dict):
                        self._deep_merge_dict(extracted_info, args)
                    tool_was_called = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": "Information captured successfully.",
                    })
                elif fname == "present_choices":
                    returned_slot = args.get("slot", "")
                    choices = args.get("choices", [])
                    if isinstance(choices, list):
                        # ── Backend validation of slot/choices alignment ──
                        if planned_slot_id and returned_slot != planned_slot_id:
                            # Slot mismatch — reject, use fallback
                            choice_validation = "rejected_mismatch"
                            logger.warning(
                                "present_choices slot mismatch: expected=%s got=%s",
                                planned_slot_id, returned_slot,
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": f"Rejected: choices must be for slot '{planned_slot_id}', not '{returned_slot}'.",
                            })
                        else:
                            sp = _get_slot_planner()
                            if sp.validate_choices_for_slot(planned_slot_id or returned_slot, choices):
                                choice_validation = "valid"
                                accepted_slot = returned_slot or planned_slot_id
                                suggested_choices.extend(choices)
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": "Choices accepted.",
                                })
                            else:
                                choice_validation = "rejected_vocab"
                                logger.warning(
                                    "present_choices vocabulary mismatch for slot=%s",
                                    planned_slot_id or returned_slot,
                                )
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": "Rejected: choices do not match the expected vocabulary for this slot.",
                                })
                    tool_was_called = True
                elif fname == "capture_additional_info":
                    if isinstance(args, dict):
                        section = args.get("section")
                        field = args.get("field")
                        value = args.get("value")
                        if section and field and value is not None:
                            converted = _convert_additional_value(field, value)
                            additional_section = extracted_info.setdefault(section, {})
                            additional_section[field] = converted
                    tool_was_called = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": "Information captured successfully.",
                    })
                else:
                    any_unknown = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": "Unknown tool. Only use the available tools.",
                    })

            # If the model already returned conversational text alongside tool calls,
            # return immediately so question text and choices stay in the same turn.
            if reply_text.strip() and not any_unknown:
                return {
                    "reply": reply_text,
                    "extracted_info": extracted_info,
                    "suggested_choices": suggested_choices,
                    "tool_was_called": tool_was_called,
                    "accepted_slot": accepted_slot,
                    "choice_validation": choice_validation,
                }

            # Tools processed — on the next iteration, force the LLM to generate
            # conversational text rather than calling more tools.
            must_generate_text = True

            if any_unknown:
                # Add an extra system hint and let the loop retry
                messages.append({
                    "role": "system",
                    "content": "Only use the available extraction tool and `present_choices` — nothing else.",
                })
                # The next iteration will still use effective_tool_choice="auto"
                # since must_generate_text was just set, but the unknown tool
                # flow needs tools available for the correction.
                must_generate_text = False

        # Fallback after max attempts
        return {
            "reply": "Could you tell me a bit more about your setup?",
            "extracted_info": extracted_info,
            "suggested_choices": suggested_choices,
            "tool_was_called": tool_was_called,
            "accepted_slot": accepted_slot,
            "choice_validation": choice_validation,
        }


_client_instance = LLMClient()


def _convert_additional_value(field: str, value: str) -> Any:
    """
    Convert string values from `capture_additional_info` to appropriate types
    for known fields. The LLM sends everything as strings, but some fields
    expect int, float, bool, or list types.
    """
    # Integer fields
    if field in ("monthly_volume",):
        try:
            return int(value.replace(",", ""))
        except (ValueError, AttributeError):
            return value
    # Float fields
    if field in ("average_ticket",):
        try:
            return float(value.replace("$", "").replace(",", ""))
        except (ValueError, AttributeError):
            return value
    # Boolean fields
    if field in ("needs_pin", "is_standalone", "needs_display"):
        lower = value.strip().lower()
        if lower in ("yes", "true", "y", "1"):
            return True
        if lower in ("no", "false", "n", "0"):
            return False
        return value
    # List fields (comma-separated)
    if field in ("card_types", "previous_products"):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return parts if parts else value
    # Default: keep as string
    return value


def process_turn(
    message: str,
    history: List[Dict[str, str]],
    state: str = "greeting",
    collected_info: Optional[Dict[str, Any]] = None,
    planned_slot_id: Optional[str] = None,
    slot_prompt_hint: Optional[str] = None,
    next_topic_hint: Optional[str] = None,
) -> Dict[str, Any]:
    return _client_instance.process_turn(
        message, history, state, collected_info,
        planned_slot_id=planned_slot_id,
        slot_prompt_hint=slot_prompt_hint,
        next_topic_hint=next_topic_hint,
    )
