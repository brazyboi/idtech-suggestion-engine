import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.agent.loop import process_message, process_message_stream
from backend.auth import issue_session_token, verify_session_token
from backend.db.repositories.event_repository import EventRepository
from backend.db.session import session_scope
from backend.engine.conversation_store import ConversationStore, get_conversation_store
from backend.engine.state_machine import ConversationSession
from backend.llm.contracts import ChatResponse
from backend.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter()

# Caps a single conversation's turns — /api/chat is unauthenticated and
# every turn costs an OpenAI call, so without a ceiling a scripted client
# reusing one session_id could still run up an unbounded bill (see D3).
MAX_SESSION_TURNS = int(os.getenv("MAX_SESSION_TURNS", "60"))

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
    session_token: str
    message: str
    stage: str


class SessionResumeResponse(BaseModel):
    session_id: str
    exists: bool
    history: List[Dict[str, str]]
    stage: Optional[str] = None


_STREAM_DONE = object()


def _next_or_done(gen):
    """
    next(gen), but returns a sentinel instead of raising StopIteration.

    A bare StopIteration can't safely cross the run_in_threadpool/asyncio
    boundary the streaming endpoint uses below — asyncio converts an
    escaping StopIteration into a RuntimeError (PEP 479), so `except
    StopIteration` around the await never actually catches it.
    """
    try:
        return next(gen)
    except StopIteration:
        return _STREAM_DONE


def _log_funnel_event(session_id: str, event_type: str) -> None:
    """Best-effort funnel logging — never let a DB hiccup break a chat turn."""
    try:
        with session_scope() as db:
            EventRepository(db).log_event(session_id, event_type)
    except Exception:
        logger.exception("Failed to log funnel event '%s' for session %s", event_type, session_id)


def _finalize_turn(
    store: ConversationStore,
    session_id: str,
    session: ConversationSession,
    is_first_turn: bool,
    was_recommendation_shown: bool,
    was_lead_submitted: bool,
) -> None:
    """
    Persist the (mutated) session and log funnel events. Shared by
    /api/chat and /api/chat/stream, and called from the streaming
    endpoint's `finally` so it still runs on a client disconnect
    mid-stream, not just on a clean finish.
    """
    store.save_session(session_id, session)

    # Funnel events — feeds the resolution-rate metric on the admin
    # dashboard (previously no conversion visibility existed at all).
    if is_first_turn:
        _log_funnel_event(session_id, "session_started")
    if not was_recommendation_shown and session.collected_info.meta.recommendation_shown:
        _log_funnel_event(session_id, "recommendation_shown")
    if not was_lead_submitted and session.lead_submitted:
        _log_funnel_event(session_id, "lead_submitted")


@router.post("/session", response_model=SessionCreateResponse)
@limiter.limit("10/minute")
async def create_session(
    request: Request,
    store: ConversationStore = Depends(get_conversation_store),
):
    session_id = store.ensure_session(None)
    return SessionCreateResponse(
        session_id=session_id,
        session_token=issue_session_token(session_id),
        message=WELCOME_MESSAGE,
        stage="greeting",
    )


@router.get("/session/{session_id}", response_model=SessionResumeResponse)
async def resume_session(
    session_id: str,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    store: ConversationStore = Depends(get_conversation_store),
):
    """
    Used by the frontend to rehydrate a conversation after a page refresh
    (session_id is persisted in localStorage). Returns the raw message
    history so far so the transcript can be redrawn.

    Requires the signed session_token issued at session creation — a bare
    session_id (logged in access logs, sitting in localStorage) isn't
    enough on its own to read someone else's transcript (see D2).
    """
    if not store.has_session(session_id):
        return SessionResumeResponse(session_id=session_id, exists=False, history=[])
    if not verify_session_token(session_id, x_session_token):
        raise HTTPException(status_code=403, detail="Missing or invalid session token")
    session = store.get_session(session_id)
    return SessionResumeResponse(
        session_id=session_id,
        exists=True,
        history=session.history,
        stage=session.intent,
    )


@router.post("/chat")
@limiter.limit("20/minute")
async def chat_endpoint(
    request: Request,
    chat_request: ChatRequest,
    store: ConversationStore = Depends(get_conversation_store),
):
    try:
        session_id = store.ensure_session(chat_request.session_id)
        session = store.get_session(session_id)  # deep copy

        if session.turn_count >= MAX_SESSION_TURNS:
            raise HTTPException(
                status_code=429,
                detail="This conversation has reached its turn limit. Please start a new session.",
            )

        is_first_turn = len(session.history) == 0
        was_recommendation_shown = session.collected_info.meta.recommendation_shown
        was_lead_submitted = session.lead_submitted

        response = process_message(
            message=chat_request.message,
            session=session,
        )

        # Serialize the response, adding the session_id.
        payload = response.model_dump(exclude_none=True)
        payload["session_id"] = session_id

        # Session was mutated in-place by process_message (history,
        # collected_info, lead_submitted, etc. are all updated).
        _finalize_turn(store, session_id, session, is_first_turn, was_recommendation_shown, was_lead_submitted)

        return payload
    except HTTPException:
        raise
    except Exception:
        logger.exception("chat_endpoint failed for session %s", chat_request.session_id)
        raise HTTPException(
            status_code=500,
            detail="Something went wrong processing your message. Please try again.",
        )


@router.post("/chat/stream")
@limiter.limit("20/minute")
async def chat_stream_endpoint(
    request: Request,
    chat_request: ChatRequest,
    store: ConversationStore = Depends(get_conversation_store),
):
    """
    Same turn as /api/chat, but streamed as Server-Sent Events so the
    client can show progress ("Searching products...") and the final
    answer's text as it's generated, instead of one blocking JSON response.

    Event shapes (each line is `data: <json>\\n\\n`):
      {"type": "progress", "stage": "tool_call"|"tool_result", "tool": str, "message": str}
      {"type": "token", "delta": str}
      {"type": "done", "response": <same JSON /api/chat returns>}
      {"type": "error", "message": str}   — only on an unhandled failure

    /api/chat is untouched and still works exactly as before — this is an
    additive endpoint, not a replacement.
    """
    session_id = store.ensure_session(chat_request.session_id)
    session = store.get_session(session_id)  # deep copy

    if session.turn_count >= MAX_SESSION_TURNS:
        raise HTTPException(
            status_code=429,
            detail="This conversation has reached its turn limit. Please start a new session.",
        )

    is_first_turn = len(session.history) == 0
    was_recommendation_shown = session.collected_info.meta.recommendation_shown
    was_lead_submitted = session.lead_submitted

    async def event_generator() -> AsyncIterator[str]:
        # Drives the (sync, blocking-on-OpenAI) generator one item at a
        # time via run_in_threadpool, rather than handing the sync
        # generator straight to StreamingResponse, so that a client
        # disconnect reliably triggers this function's `finally` — Starlette
        # closes an async generator (awaiting aclose(), which raises
        # GeneratorExit here) when it wins the race against the stream
        # finishing, but doesn't guarantee closing a wrapped sync one.
        gen = process_message_stream(chat_request.message, session)
        try:
            while True:
                event = await run_in_threadpool(_next_or_done, gen)
                if event is _STREAM_DONE:
                    break

                if event["type"] == "token":
                    yield f"data: {json.dumps({'type': 'token', 'delta': event['delta']})}\n\n"
                elif event["type"] == "progress":
                    yield f"data: {json.dumps({'type': 'progress', 'stage': event['stage'], 'tool': event.get('tool'), 'message': event.get('message')})}\n\n"
                elif event["type"] == "done":
                    payload = event["response"].model_dump(exclude_none=True)
                    payload["session_id"] = session_id
                    yield f"data: {json.dumps({'type': 'done', 'response': payload})}\n\n"
        except Exception:
            logger.exception("chat_stream_endpoint failed for session %s", session_id)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Something went wrong processing your message. Please try again.'})}\n\n"
        finally:
            gen.close()
            # Persist + log funnel events even if the client disconnected
            # mid-stream — otherwise a turn that got most of the way through
            # (e.g. submit_lead already ran) would silently not be saved.
            _finalize_turn(store, session_id, session, is_first_turn, was_recommendation_shown, was_lead_submitted)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )