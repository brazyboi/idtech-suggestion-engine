import os
import logging
from urllib.parse import urlsplit
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

DEFAULT_DB_URL = "postgresql://admin:ics1802026@localhost:5432/product_db"
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


DB_URL = _normalize_db_url(os.environ.get("DATABASE_URL", DEFAULT_DB_URL))
parsed_db = urlsplit(DB_URL)
logger.warning(
    "Database target host=%s port=%s db=%s",
    parsed_db.hostname,
    parsed_db.port,
    parsed_db.path.lstrip("/"),
)

engine = create_engine(DB_URL, echo=True)
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
