import os
import logging
from contextlib import contextmanager
from urllib.parse import urlsplit
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, Iterator

logger = logging.getLogger(__name__)


def _normalize_db_url(db_url: str) -> str:
    """
    Keep URL normalization minimal and non-destructive.
    We do NOT rewrite hostnames (e.g., db -> localhost), because that can break
    Docker Compose networking and cause hard-to-debug auth failures.
    """
    parsed = urlsplit(db_url)
    host = parsed.hostname or ""
    port = parsed.port

    # If user omitted port on localhost, default to 5432.
    if host in {"localhost", "127.0.0.1"} and port is None:
        return db_url.replace("@localhost/", "@localhost:5432/").replace("@127.0.0.1/", "@127.0.0.1:5432/")

    return db_url


# Fail fast without a database URL; SKIP_STARTUP_CHECKS=1 supports tooling imports.
if not os.getenv("DATABASE_URL") and not os.getenv("SKIP_STARTUP_CHECKS"):
    raise RuntimeError(
        "DATABASE_URL is not set. Copy backend/.env.example to backend/.env "
        "and set it before starting the server."
    )

DB_URL = _normalize_db_url(os.environ.get("DATABASE_URL", "postgresql://localhost:5432/product_db"))
parsed_db = urlsplit(DB_URL)
logger.info(
    "Database target host=%s port=%s db=%s",
    parsed_db.hostname,
    parsed_db.port,
    parsed_db.path.lstrip("/"),
)

# SQL echo is a verbose, per-statement log — opt in with SQL_ECHO=1 for local
# debugging, off by default so it doesn't spam production logs.
engine = create_engine(DB_URL, echo=bool(os.getenv("SQL_ECHO")))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to provide a database session for each request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    Context-managed session for code outside the FastAPI request cycle
    (agent tools, services) that can't use the `get_db` Depends() path.
    Centralizes session creation so it's one place to swap/mock in tests,
    instead of every call site importing SessionLocal directly.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
