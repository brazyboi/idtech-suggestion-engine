"""
Integration tests for the FastAPI routers, exercised end-to-end through
the real ASGI app via TestClient (see conftest.api_client / db_session).

Before this file existed, test_api.py was a one-line TODO stub — meaning
none of the actual HTTP surface (the thing sponsors will click through)
had any test coverage at all. These tests hit real endpoints against an
in-memory SQLite DB; the only thing mocked is the OpenAI call inside
process_message, since that's an external network dependency.
"""

import json
from unittest.mock import patch

from backend.llm.contracts import ChatResponse


# ── /api/session ─────────────────────────────────────────────────────

class TestCreateSession:
    def test_returns_a_session_id_and_greeting(self, api_client):
        resp = api_client.post("/api/session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"]
        assert body["stage"] == "greeting"
        assert "message" in body


# ── /api/chat ─────────────────────────────────────────────────────────

class TestChatEndpoint:
    def test_happy_path_returns_response_with_session_id(self, api_client):
        fake_response = ChatResponse(type="clarification", text="Hi there!")
        with patch("backend.routers.chat.process_message", return_value=fake_response) as mock_process:
            resp = api_client.post("/api/chat", json={"message": "hello"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "Hi there!"
        assert body["session_id"]
        mock_process.assert_called_once()

    def test_reuses_existing_session_id_when_provided(self, api_client):
        create_resp = api_client.post("/api/session")
        session_id = create_resp.json()["session_id"]

        fake_response = ChatResponse(type="clarification", text="Still here")
        with patch("backend.routers.chat.process_message", return_value=fake_response):
            resp = api_client.post("/api/chat", json={"message": "hi", "session_id": session_id})

        assert resp.status_code == 200
        assert resp.json()["session_id"] == session_id

    def test_persists_session_mutations_across_turns(self, api_client):
        """process_message mutates session.turn_count in place; the store
        must actually persist that mutation, or every turn would look like
        the conversation's first turn."""

        def _bump_turn_count(message, session):
            session.turn_count += 1
            return ChatResponse(type="clarification", text=f"turn {session.turn_count}")

        with patch("backend.routers.chat.process_message", side_effect=_bump_turn_count):
            first = api_client.post("/api/chat", json={"message": "one"})
            session_id = first.json()["session_id"]
            second = api_client.post("/api/chat", json={"message": "two", "session_id": session_id})

        assert first.json()["text"] == "turn 1"
        assert second.json()["text"] == "turn 2"

    def test_missing_message_field_is_rejected_with_422(self, api_client):
        resp = api_client.post("/api/chat", json={})
        assert resp.status_code == 422

    def test_unhandled_exception_returns_500_without_leaking_internals(self, api_client):
        """An unexpected error in process_message must become a generic 500,
        not tear down the server, and must NOT echo the raw exception
        message (which could contain internal details like DB errors)
        back to the client."""
        with patch("backend.routers.chat.process_message", side_effect=RuntimeError("super secret internal detail")):
            resp = api_client.post("/api/chat", json={"message": "hello"})

        assert resp.status_code == 500
        assert "super secret internal detail" not in resp.text


# ── /api/maintenance/hardware ────────────────────────────────────────

class TestHardwareMaintenanceEndpoints:
    def test_create_then_get_hardware(self, api_client):
        create_resp = api_client.post(
            "/api/maintenance/hardware",
            json={"model_name": "VP3300", "input_power": "USB", "categories": [], "use_cases": [], "software": []},
        )
        assert create_resp.status_code == 201
        assert create_resp.json()["model_name"] == "VP3300"

        get_resp = api_client.get("/api/maintenance/hardware/VP3300")
        assert get_resp.status_code == 200
        assert get_resp.json()["input_power"] == "USB"

    def test_get_missing_hardware_returns_404(self, api_client):
        resp = api_client.get("/api/maintenance/hardware/does-not-exist")
        assert resp.status_code == 404

    def test_create_duplicate_hardware_returns_409(self, api_client):
        payload = {"model_name": "VP3300", "categories": [], "use_cases": [], "software": []}
        api_client.post("/api/maintenance/hardware", json=payload)
        resp = api_client.post("/api/maintenance/hardware", json=payload)
        assert resp.status_code == 409

    def test_create_with_unknown_category_returns_400(self, api_client):
        resp = api_client.post(
            "/api/maintenance/hardware",
            json={"model_name": "VP3300", "categories": ["Nonexistent"], "use_cases": [], "software": []},
        )
        assert resp.status_code == 400

    def test_update_hardware_patches_fields(self, api_client):
        api_client.post(
            "/api/maintenance/hardware",
            json={"model_name": "VP3300", "input_power": "USB", "categories": [], "use_cases": [], "software": []},
        )
        resp = api_client.patch("/api/maintenance/hardware/VP3300", json={"input_power": "VAC"})
        assert resp.status_code == 200
        assert resp.json()["input_power"] == "VAC"

    def test_delete_hardware_soft_deletes_it(self, api_client):
        api_client.post(
            "/api/maintenance/hardware",
            json={"model_name": "VP3300", "categories": [], "use_cases": [], "software": []},
        )
        delete_resp = api_client.delete("/api/maintenance/hardware/VP3300")
        assert delete_resp.status_code == 204

        get_resp = api_client.get("/api/maintenance/hardware/VP3300")
        assert get_resp.status_code == 404


# ── /api/lead ─────────────────────────────────────────────────────────

class TestLeadEndpoints:
    def test_request_call_creates_a_lead(self, api_client, patch_direct_db_access):
        resp = api_client.post(
            "/api/lead/request-call",
            json={"name": "Alice", "email": "alice@example.com"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["lead_id"]

    def test_list_leads_returns_created_lead(self, api_client, patch_direct_db_access):
        api_client.post("/api/lead/request-call", json={"name": "Alice", "email": "alice@example.com"})

        resp = api_client.get("/api/lead/leads")
        assert resp.status_code == 200
        leads = resp.json()
        assert len(leads) == 1
        assert leads[0]["name"] == "Alice"

    def test_get_single_lead_by_id(self, api_client, patch_direct_db_access):
        create_resp = api_client.post("/api/lead/request-call", json={"name": "Bob", "email": "bob@example.com"})
        lead_id = create_resp.json()["lead_id"]

        resp = api_client.get(f"/api/lead/leads/{lead_id}")
        assert resp.status_code == 200
        assert resp.json()["email"] == "bob@example.com"

    def test_get_missing_lead_returns_404(self, api_client):
        resp = api_client.get("/api/lead/leads/999999")
        assert resp.status_code == 404


# ── D1: admin auth gate on /api/lead/* and /api/maintenance/* ──────────

class TestAdminAuthGate:
    def test_list_leads_without_key_returns_401(self, unauthed_api_client):
        resp = unauthed_api_client.get("/api/lead/leads")
        assert resp.status_code == 401

    def test_list_leads_with_wrong_key_returns_401(self, unauthed_api_client):
        resp = unauthed_api_client.get("/api/lead/leads", headers={"X-Admin-Api-Key": "wrong"})
        assert resp.status_code == 401

    def test_list_leads_with_correct_key_succeeds(self, api_client):
        resp = api_client.get("/api/lead/leads")
        assert resp.status_code == 200

    def test_maintenance_hardware_without_key_returns_401(self, unauthed_api_client):
        resp = unauthed_api_client.get("/api/maintenance/hardware/does-not-exist")
        assert resp.status_code == 401

    def test_maintenance_hardware_create_without_key_returns_401(self, unauthed_api_client):
        resp = unauthed_api_client.post(
            "/api/maintenance/hardware",
            json={"model_name": "VP3300", "categories": [], "use_cases": [], "software": []},
        )
        assert resp.status_code == 401

    def test_chat_and_session_remain_public(self, unauthed_api_client):
        """/api/chat and /api/session must stay unauthenticated — they're the public widget."""
        resp = unauthed_api_client.post("/api/session")
        assert resp.status_code == 200


# ── D2: session tokens gate GET /api/session/{id} ──────────────────────

class TestSessionTokenAuth:
    def test_create_session_returns_a_token(self, api_client):
        resp = api_client.post("/api/session")
        assert resp.status_code == 200
        assert resp.json()["session_token"]

    def test_resume_without_token_is_rejected(self, api_client):
        create_resp = api_client.post("/api/session")
        session_id = create_resp.json()["session_id"]

        resp = api_client.get(f"/api/session/{session_id}")
        assert resp.status_code == 403

    def test_resume_with_wrong_token_is_rejected(self, api_client):
        create_resp = api_client.post("/api/session")
        session_id = create_resp.json()["session_id"]

        resp = api_client.get(
            f"/api/session/{session_id}", headers={"X-Session-Token": "wrong"}
        )
        assert resp.status_code == 403

    def test_resume_with_correct_token_succeeds(self, api_client):
        create_resp = api_client.post("/api/session")
        session_id = create_resp.json()["session_id"]
        token = create_resp.json()["session_token"]

        resp = api_client.get(
            f"/api/session/{session_id}", headers={"X-Session-Token": token}
        )
        assert resp.status_code == 200
        assert resp.json()["exists"] is True

    def test_resume_missing_session_returns_exists_false_regardless_of_token(self, api_client):
        """A nonexistent session_id shouldn't leak whether a token would have
        been valid — it should just say exists: False, same as before D2."""
        resp = api_client.get("/api/session/does-not-exist")
        assert resp.status_code == 200
        assert resp.json()["exists"] is False


# ── D3: per-IP rate limiting and per-session turn cap ───────────────────

class TestRateLimiting:
    def test_session_creation_is_rate_limited(self, api_client):
        responses = [api_client.post("/api/session") for _ in range(11)]
        assert responses[-1].status_code == 429

    def test_chat_turn_cap_returns_429(self, api_client):
        from backend.routers.chat import MAX_SESSION_TURNS

        create_resp = api_client.post("/api/session")
        session_id = create_resp.json()["session_id"]

        def _bump_turn_count(message, session):
            session.turn_count = MAX_SESSION_TURNS
            return ChatResponse(type="clarification", text="ok")

        with patch("backend.routers.chat.process_message", side_effect=_bump_turn_count):
            first = api_client.post("/api/chat", json={"message": "hi", "session_id": session_id})
            assert first.status_code == 200

            second = api_client.post("/api/chat", json={"message": "hi again", "session_id": session_id})
            assert second.status_code == 429


# ── /api/chat/stream ─────────────────────────────────────────────────

def _sse_events(resp) -> list:
    """Parse `data: <json>\\n\\n` lines out of an SSE response body."""
    events = []
    for line in resp.text.split("\n\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


class TestChatStreamEndpoint:
    def test_forwards_progress_token_and_done_events(self, api_client):
        fake_response = ChatResponse(type="clarification", text="Hi there!")

        def fake_stream(message, session):
            yield {"type": "progress", "stage": "tool_call", "tool": "search_products", "message": "Searching products..."}
            yield {"type": "progress", "stage": "tool_result", "tool": "search_products"}
            yield {"type": "token", "delta": "Hi "}
            yield {"type": "token", "delta": "there!"}
            yield {"type": "done", "response": fake_response}

        with patch("backend.routers.chat.process_message_stream", side_effect=fake_stream):
            resp = api_client.post("/api/chat/stream", json={"message": "hello"})

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(resp)
        assert events[0] == {"type": "progress", "stage": "tool_call", "tool": "search_products", "message": "Searching products..."}
        assert events[2] == {"type": "token", "delta": "Hi "}
        assert events[-1]["type"] == "done"
        assert events[-1]["response"]["text"] == "Hi there!"
        assert events[-1]["response"]["session_id"]

    def test_persists_session_and_reuses_session_id(self, api_client):
        def _bump_turn_count(message, session):
            session.turn_count += 1
            yield {"type": "done", "response": ChatResponse(type="clarification", text=f"turn {session.turn_count}")}

        with patch("backend.routers.chat.process_message_stream", side_effect=_bump_turn_count):
            first = api_client.post("/api/chat/stream", json={"message": "one"})
            session_id = _sse_events(first)[-1]["response"]["session_id"]
            second = api_client.post("/api/chat/stream", json={"message": "two", "session_id": session_id})

        assert _sse_events(first)[-1]["response"]["text"] == "turn 1"
        assert _sse_events(second)[-1]["response"]["text"] == "turn 2"

    def test_turn_cap_returns_429_before_streaming_starts(self, api_client):
        from backend.routers.chat import MAX_SESSION_TURNS

        create_resp = api_client.post("/api/session")
        session_id = create_resp.json()["session_id"]

        def _bump_turn_count(message, session):
            session.turn_count = MAX_SESSION_TURNS
            yield {"type": "done", "response": ChatResponse(type="clarification", text="ok")}

        with patch("backend.routers.chat.process_message_stream", side_effect=_bump_turn_count):
            first = api_client.post("/api/chat/stream", json={"message": "hi", "session_id": session_id})
            assert first.status_code == 200

            second = api_client.post("/api/chat/stream", json={"message": "hi again", "session_id": session_id})
            assert second.status_code == 429

    def test_unhandled_exception_emits_error_event_not_a_crash(self, api_client):
        def _blow_up(message, session):
            yield {"type": "token", "delta": "partial"}
            raise RuntimeError("super secret internal detail")

        with patch("backend.routers.chat.process_message_stream", side_effect=_blow_up):
            resp = api_client.post("/api/chat/stream", json={"message": "hello"})

        assert resp.status_code == 200  # SSE headers already sent by the time the error happens
        events = _sse_events(resp)
        assert events[0] == {"type": "token", "delta": "partial"}
        assert events[-1]["type"] == "error"
        assert "super secret internal detail" not in resp.text

    def test_funnel_events_logged_even_on_mid_stream_failure(self, api_client, patch_direct_db_access):
        """The session and funnel events must still be persisted via the
        generator's `finally` even when the turn raises partway through —
        not just on a clean finish."""
        from backend.db.repositories.event_repository import EventRepository

        def _blow_up(message, session):
            yield {"type": "token", "delta": "partial"}
            raise RuntimeError("boom")

        with patch("backend.routers.chat.process_message_stream", side_effect=_blow_up):
            resp = api_client.post("/api/chat/stream", json={"message": "hello"})

        assert resp.status_code == 200
        counts = EventRepository(patch_direct_db_access()).funnel_counts()
        assert counts["session_started"] == 1
