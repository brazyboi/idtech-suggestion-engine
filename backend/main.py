import logging
import os
import sys
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Ensure the project root is on sys.path so absolute imports resolve,
# regardless of whether we run `uvicorn main:app` (from backend/)
# or `uvicorn backend.main:app` (from project root) or `python -m uvicorn ...`
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Load environment variables before importing routers
load_dotenv()

# Fail fast on missing config: without this, the app boots "successfully"
# and every chat request silently falls back to a fake "test-key" (see
# agent/classifier.py and agent/loop.py), which only surfaces as a
# confusing OpenAI auth error deep inside a request instead of an obvious
# startup failure. Set SKIP_STARTUP_CHECKS=1 to bypass (e.g. for tooling
# that imports this module without needing the chat feature to work).
if not os.getenv("SKIP_STARTUP_CHECKS"):
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY")):
        raise RuntimeError(
            "OPENAI_API_KEY (or OPENAI_ADMIN_KEY) is not set. The chat agent "
            "cannot function without it. Set it in the environment or a .env "
            "file before starting the server."
        )
    # Without these, /api/lead/* and /api/maintenance/* would boot with no
    # admin gate (see backend/auth.py) and session transcripts would be
    # readable by anyone holding a session_id — both silent PII leaks
    # rather than an obvious startup failure.
    if not os.getenv("ADMIN_API_KEY"):
        raise RuntimeError(
            "ADMIN_API_KEY is not set. Admin/lead endpoints cannot be safely "
            "exposed without it. Set it in the environment or a .env file "
            "before starting the server."
        )
    if not os.getenv("SESSION_SECRET_KEY"):
        raise RuntimeError(
            "SESSION_SECRET_KEY is not set. Session transcripts cannot be "
            "safely served without it. Set it in the environment or a .env "
            "file before starting the server."
        )

logger = logging.getLogger(__name__)

from backend.auth import require_admin_key
from backend.rate_limit import limiter
from backend.routers import chat, pdf
from backend.routers import lead as lead_router
from backend.routers.maintenance import hardware, software, prompts, docs

app = FastAPI(title="ID TECH Suggestion Engine")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS middleware. Origins come from CORS_ALLOW_ORIGINS (comma-separated)
# so the widget can be embedded on idtechproducts.com without a code change
# — set it to the real site origin(s) at deploy time. Defaults to the Vite
# dev server so local development needs no configuration.
#
# allow_credentials is False: nothing in this app uses cookies (auth is a
# header-based API key / session token, see auth.py), and leaving it True
# would block a wildcard origin if staging ever needs one.
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
