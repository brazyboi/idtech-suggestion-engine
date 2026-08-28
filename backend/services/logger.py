"""
Reasoning trace logger for the agentic loop.

Provides structured logging of every agent decision — intent classification,
tool calls, tool results, and final responses — so the system is observable
and debuggable.
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReasoningTrace:
    """
    Collects a step-by-step trace of the agent's reasoning for a single turn.

    This is appended to the session's reasoning_trace list after each turn.
    """

    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        self.start_time = time.time()
        self.steps: List[Dict[str, Any]] = []

    def add_step(self, kind: str, detail: Dict[str, Any]) -> None:
        """Record a reasoning step."""
        self.steps.append({
            "kind": kind,
            "timestamp": time.time(),
            **detail,
        })

    def intent_classified(self, intent: str, confidence: float, entities: Dict[str, Any]) -> None:
        """Log intent classification result."""
        self.add_step("intent_classification", {
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
        })

    def tool_called(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """Log a tool invocation."""
        self.add_step("tool_call", {
            "tool": tool_name,
            "arguments": arguments,
        })

    def tool_result(self, tool_name: str, result_summary: str, success: bool = True) -> None:
        """Log the result of a tool call."""
        self.add_step("tool_result", {
            "tool": tool_name,
            "summary": result_summary,
            "success": success,
        })

    def response_generated(self, response_type: str, text_preview: str) -> None:
        """Log the final response."""
        self.add_step("response", {
            "type": response_type,
            "text_preview": text_preview[:200],
        })

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the trace to a dict for session storage."""
        return {
            "turn_id": self.turn_id,
            "elapsed_ms": int((time.time() - self.start_time) * 1000),
            "steps": self.steps,
        }

    def log_to_console(self) -> None:
        """Pretty-print the trace to the console for local debugging."""
        elapsed = int((time.time() - self.start_time) * 1000)
        logger.info("── Turn %s (%dms) ──", self.turn_id, elapsed)
        for step in self.steps:
            kind = step.pop("kind")
            logger.info("  [%s] %s", kind, step)
