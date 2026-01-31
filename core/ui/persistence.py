from __future__ import annotations

import os

from core import config
from core.logging_config import logger
from core.persistence import create_history_store
from core.persistence.types import HistoryStore


def _get_postgres_dsn(st) -> str:
    # Prefer Streamlit secrets (Community Cloud)
    try:
        supabase = st.secrets.get("supabase", {})
        postgres = st.secrets.get("postgres", {})
        dsn = (
            supabase.get("db_url")
            or supabase.get("database_url")
            or postgres.get("dsn")
            or postgres.get("db_url")
            or ""
        )
        if dsn:
            return str(dsn)
    except Exception:
        pass

    return (
        os.getenv("SUPABASE_DB_URL", "")
        or os.getenv("POSTGRES_DSN", "")
        or os.getenv("DATABASE_URL", "")
    ).strip()


def init_history_store(st, *, user_key: str) -> HistoryStore:
    postgres_dsn = _get_postgres_dsn(st)
    store = create_history_store(
        user_key=user_key,
        postgres_dsn=postgres_dsn,
        retention_days=config.RETENTION_DAYS,
    )

    # Streamlit Cloudではローカルファイルは永続ではない（設定漏れの即時検知）
    # production flagに依存せず「postgresを期待しているのにlocalになった」場合に警告する
    if store.__class__.__name__ == "LocalHistoryStore" and config.SESSION_STORE_BACKEND in {"auto", "postgres", "supabase"}:
        st.sidebar.warning(
            "⚠️ 永続ストレージが未設定です。Streamlit Cloudのファイルは永続されません。\n"
            "Supabase(Postgres)のDSNを `secrets` に設定してください。"
        )

    # Retention cleanup: run once per session
    if "retention_cleanup_done" not in st.session_state:
        try:
            store.cleanup_retention()
        except Exception:
            logger.exception("retention cleanup failed")
        st.session_state.retention_cleanup_done = True

    return store

