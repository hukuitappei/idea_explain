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
        # If we fell back due to connection failure, show reason and hints (no secrets).
        if getattr(store, "_postgres_unavailable", False):
            reason = getattr(store, "_postgres_unavailable_reason", "(unknown)")
            st.sidebar.error(
                "Postgres接続に失敗したため、ローカル保存にフォールバックしました。\n"
                f"原因（要約）: {reason}\n\n"
                "よくある原因:\n"
                "- DSNがテンプレのまま（<host>/<password>）\n"
                "- DBパスワード未設定/誤り\n"
                "- IPv6アドレスへ接続しようとして失敗（Cannot assign requested address）\n"
                "対策:\n"
                "- SupabaseのConnection stringをそのまま貼る（hostは通常 db.<ref>.supabase.co）\n"
                "- うまく行かない場合は Supabase の Pooler（6543）を使う/IPv4で接続する"
            )

    # Retention cleanup: run once per session
    if "retention_cleanup_done" not in st.session_state:
        try:
            store.cleanup_retention()
        except Exception:
            logger.exception("retention cleanup failed")
        st.session_state.retention_cleanup_done = True

    return store

