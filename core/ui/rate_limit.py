from __future__ import annotations

from core.logging_config import logger
from core.persistence.types import RateLimitExceededError


def consume_llm_quota_or_stop(st, *, history_store, daily_limit: int) -> None:
    try:
        history_store.consume_llm_request(daily_limit)
    except RateLimitExceededError as e:
        st.error(str(e))
        st.stop()
    except Exception:
        logger.exception("rate limit check failed")
        st.error("レート制限の確認に失敗しました。時間をおいて再試行してください。")
        st.stop()

