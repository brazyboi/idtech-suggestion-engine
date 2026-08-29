"""
Auth helpers.

D1: /api/lead/* and /api/maintenance/* are admin-only surfaces (lead PII,
catalog mutation) gated behind a shared-secret API key. Minimum viable
gate for an internal admin tool; swap for real SSO at handoff.

D2: session transcripts (GET /api/session/{id}) are gated by a signed
token issued at session creation, so a session_id alone (logged in
access logs, sitting in localStorage) isn't enough to read someone
else's transcript.
"""
import hashlib
import hmac
import os

from fastapi import Header, HTTPException, status

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")


def require_admin_key(x_admin_api_key: str = Header(default=None, alias="X-Admin-Api-Key")) -> None:
    if not ADMIN_API_KEY or not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, ADMIN_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid admin API key")


def issue_session_token(session_id: str) -> str:
    return hmac.new(SESSION_SECRET_KEY.encode(), session_id.encode(), hashlib.sha256).hexdigest()


def verify_session_token(session_id: str, token: str | None) -> bool:
    if not token or not SESSION_SECRET_KEY:
        return False
    return hmac.compare_digest(issue_session_token(session_id), token)
