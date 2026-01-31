from __future__ import annotations

from core import config
from core.logging_config import logger

from .local_store import LocalHistoryStore
from .postgres_store import PostgresHistoryStore
from .types import HistoryStore


def create_history_store(*, user_key: str, postgres_dsn: str | None, retention_days: int) -> HistoryStore:
    """Create a per-user history store.

    - Production (Streamlit Cloud): prefer Postgres (Supabase)
    - Fallback: local files (NOT durable on Streamlit Cloud)
    """

    backend = (getattr(config, "SESSION_STORE_BACKEND", "") or "").strip().lower()
    if backend in {"", "auto"}:
        # Auto: if DSN is present, use Postgres; else local
        backend = "postgres" if (postgres_dsn or "").strip() else "local"

    dsn = (postgres_dsn or "").strip()

    if backend in {"postgres", "supabase"}:
        if dsn:
            try:
                return PostgresHistoryStore(dsn=dsn, user_key=user_key, retention_days=retention_days)
            except Exception as e:
                # Do not crash the whole app; fall back and surface guidance in UI.
                logger.exception("Postgres store init failed; falling back to local store")
                store = LocalHistoryStore(user_key=user_key)
                setattr(store, "_postgres_unavailable_reason", str(e)[:500])
                setattr(store, "_postgres_unavailable", True)
                return store
        logger.warning("SESSION_STORE_BACKEND is postgres but DSN is missing; falling back to local store")
        store = LocalHistoryStore(user_key=user_key)
        setattr(store, "_postgres_unavailable_reason", "DSN is missing")
        setattr(store, "_postgres_unavailable", True)
        return store

    return LocalHistoryStore(user_key=user_key)

