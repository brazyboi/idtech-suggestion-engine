import logging
import os
import sys
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Support both `uvicorn main:app` and `uvicorn backend.main:app` imports.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load environment variables before importing routers
load_dotenv()

# Fail fast on missing config; set SKIP_STARTUP_CHECKS=1 for tooling imports.

# Reject the public placeholder shipped in .env.example (H5).
_PLACEHOLDER_SECRET = "change-me-to-a-random-secret"

if not os.getenv("SKIP_STARTUP_CHECKS"):
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY")):
        raise RuntimeError(
            "OPENAI_API_KEY (or OPENAI_ADMIN_KEY) is not set. The chat agent "
            "cannot function without it. Set it in the environment or a .env "
            "file before starting the server."
        )
    # These secrets protect admin endpoints and session transcripts.
    if not os.getenv("ADMIN_API_KEY"):
        raise RuntimeError(
            "ADMIN_API_KEY is not set. Admin/lead endpoints cannot be safely "
            "exposed without it. Set it in the environment or a .env file "
            "before starting the server."
        )
    if os.getenv("ADMIN_API_KEY") == _PLACEHOLDER_SECRET:
        raise RuntimeError(
            "ADMIN_API_KEY is still set to the placeholder value from "
            "backend/.env.example ('change-me-to-a-random-secret'). Generate "
            "a real secret (e.g. `openssl rand -hex 32`) before starting the "
            "server."
        )
    if not os.getenv("SESSION_SECRET_KEY"):
        raise RuntimeError(
            "SESSION_SECRET_KEY is not set. Session transcripts cannot be "
            "safely served without it. Set it in the environment or a .env "
            "file before starting the server."
        )
    if os.getenv("SESSION_SECRET_KEY") == _PLACEHOLDER_SECRET:
        raise RuntimeError(
            "SESSION_SECRET_KEY is still set to the placeholder value from "
            "backend/.env.example ('change-me-to-a-random-secret'). Generate "
            "a real secret (e.g. `openssl rand -hex 32`) before starting the "
            "server."
        )

logger = logging.getLogger(__name__)

from sqlalchemy import text

from backend.auth import require_admin_key
from backend.db.session import session_scope
from backend.engine.conversation_store import get_conversation_store
from backend.rate_limit import limiter
from backend.routers import chat, pdf
from backend.routers import lead as lead_router
from backend.routers.maintenance import hardware, software, prompts, docs

app = FastAPI(title="ID TECH Suggestion Engine")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS origins come from CORS_ALLOW_ORIGINS; auth uses headers, not cookies.
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
logger.info("CORS allowed origins: %s", _cors_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Customer Routes — public, no auth (must stay that way for the chat widget)
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(pdf.router, prefix="/api/pdf", tags=["PDF"])

# Admin routes — lead PII and catalog mutation, gated behind ADMIN_API_KEY (D1)
app.include_router(
    lead_router.router, prefix="/api/lead", tags=["Lead"],
    dependencies=[Depends(require_admin_key)],
)

# Maintenance Routes
_admin_dep = [Depends(require_admin_key)]
app.include_router(hardware.router, prefix="/api/maintenance/hardware", tags=["Maintenance Hardware"], dependencies=_admin_dep)
app.include_router(software.router, prefix="/api", tags=["Maintenance Software"], dependencies=_admin_dep) # router in software.py contains "maintenance" prefix
app.include_router(prompts.router, prefix="/api/maintenance/prompts", tags=["Maintenance Prompts"], dependencies=_admin_dep)
app.include_router(docs.router, prefix="/api/maintenance/docs", tags=["Maintenance Docs"], dependencies=_admin_dep)

@app.get("/")
async def root():
    return {"message": "ID TECH Suggestion Engine API is running"}


@app.get("/ready")
async def readiness():
    """
    Readiness probe (H4) — actively checks the DB and conversation-store
    (Redis, when configured) dependencies so an orchestrator (k8s, ECS,
    ...) can stop routing traffic to an instance that can't actually serve
    a request, rather than only checking the process is alive.

    Deliberately unauthenticated (orchestrators can't present credentials)
    and leaks nothing beyond a boolean per check — no connection strings,
    hostnames, or credentials in the response.
    """
    db_ok = False
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.exception("Readiness check: database unreachable")

    redis_ok = False
    try:
        redis_ok = get_conversation_store().ping()
    except Exception:
        logger.exception("Readiness check: conversation store unreachable")

    checks = {"db": db_ok, "redis": redis_ok}
    status = "ok" if all(checks.values()) else "unhealthy"
    body = {"status": status, "checks": checks}
    return JSONResponse(status_code=200 if status == "ok" else 503, content=body)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
