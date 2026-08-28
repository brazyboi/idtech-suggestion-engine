from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.agent.loop import process_message
from backend.engine.conversation_store import ConversationStore, get_conversation_store
from backend.llm.contracts import ChatResponse

router = APIRouter()

WELCOME_MESSAGE = (
    "Hi, I'm ID TECH Agent! I can help answer your questions "
    "and connect you with our sales experts. Ask me things like 'Can I chat with a sales "
    "expert?' or describe your business and use case!"
)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class SessionCreateResponse(BaseModel):
    session_id: str
    message: str
    stage: str


@router.post("/session", response_model=SessionCreateResponse)
async def create_session(
    store: ConversationStore = Depends(get_conversation_store),
):
    session_id = store.ensure_session(None)
    return SessionCreateResponse(
        session_id=session_id,
        message=WELCOME_MESSAGE,
        stage="greeting",
    )


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    store: ConversationStore = Depends(get_conversation_store),
):
    try:
        session_id = store.ensure_session(request.session_id)
        session = store.get_session(session_id)  # deep copy

        response = process_message(
            message=request.message,
            session=session,
        )

        # Serialize the response, adding the session_id.
        payload = response.model_dump(exclude_none=True)
        payload["session_id"] = session_id

        # Session was mutated in-place by process_message (history,
        # collected_info, lead_submitted, etc. are all updated).
        store.save_session(session_id, session)

        return payload
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))