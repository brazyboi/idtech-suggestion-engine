from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..engine.solution_schemas import RecommendationBundle
from ..engine.state_machine import ConversationState


ResponseType = Literal["question", "recommendation", "clarification", "error"]


class DebugTrace(BaseModel):
    turn_id: str
    selected_tools: List[str] = []
    constraints_used: Dict[str, Any] = {}
    rows_returned: int = 0
    relaxation_steps: List[str] = []
    final_response_type: ResponseType
    mismatch_detected: bool = False
    attempt_count: int = 0
    # Slot planner trace fields
    planned_slot: Optional[str] = None
    accepted_slot: Optional[str] = None
    choice_validation_result: Optional[str] = None  # "valid" | "rejected_mismatch" | "rejected_vocab" | "fallback"
    parser_used: Optional[str] = None  # "boolean" | "number" | "volume_ticket" | "choice" | None
    parser_succeeded: bool = False

    model_config = ConfigDict(extra="forbid")


class ChatResponse(BaseModel):
    type: ResponseType
    text: str
    quick_replies: Optional[List[str]] = None
    recommendation: Optional[RecommendationBundle] = None
    ui_actions: List[str] = Field(default_factory=list)
    new_info: Dict[str, Any] = Field(default_factory=dict)
    next_state: Optional[ConversationState] = None
    debug: Optional[DebugTrace] = Field(default=None)
    debug_match: Optional[Dict[str, Any]] = None
    # Slot planner surface fields (for frontend debugging)
    planned_slot: Optional[str] = None
    accepted_slot: Optional[str] = None
    choice_validation_result: Optional[str] = None

    model_config = ConfigDict(extra="forbid")
