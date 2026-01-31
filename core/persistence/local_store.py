from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from core import config
from core.history_mgr import HistoryManager
from core.logging_config import logger
from core.schemas import Flowchart

from .types import HistoryStore, RateLimitExceededError
from .user_key import to_user_dir_key


class LocalHistoryStore(HistoryStore):
    """File-based persistence, scoped per-user by directory."""

    def __init__(self, *, user_key: str):
        self.user_key = user_key or "anonymous"
        user_dir = to_user_dir_key(self.user_key)

        self._mgr = HistoryManager(
            storage_dir=str(Path("storage/sessions") / user_dir),
            toon_dir=str(Path("storage/toon_files") / user_dir),
        )

        self._rate_dir = Path("storage/rate_limits")
        self._rate_dir.mkdir(parents=True, exist_ok=True)
        self._rate_file = (self._rate_dir / f"{user_dir}.json").resolve()

    # ---- HistoryStore API ----

    def list_sessions(self) -> List[str]:
        return self._mgr.list_sessions()

    def save_session(self, session_id: str, history: List[Flowchart]) -> None:
        self._mgr.save_session(session_id, history)

    def load_session(self, session_id: str) -> List[Flowchart]:
        return self._mgr.load_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        if not config.SESSION_ID_PATTERN.match(session_id or ""):
            raise ValueError("無効なセッション名です")

        json_path = (self._mgr.storage_dir / f"{session_id}.json").resolve()
        toon_path = (self._mgr.toon_dir / f"{session_id}.md").resolve()

        deleted_any = False
        for p in (json_path, toon_path):
            try:
                if p.exists():
                    p.unlink()
                    deleted_any = True
            except Exception:
                logger.exception("ローカル削除に失敗: %s", str(p))
        return deleted_any

    def list_toon_files(self) -> List[str]:
        return self._mgr.list_toon_files()

    def save_toon_file(self, session_id: str, flowchart: Flowchart) -> None:
        self._mgr.save_toon_file(session_id, flowchart)

    def load_toon_file(self, session_id: str) -> Optional[Flowchart]:
        return self._mgr.load_toon_file(session_id)

    def append_toon_log(self, session_id: str, new_flowchart: Flowchart) -> Flowchart:
        return self._mgr.append_toon_log(session_id, new_flowchart)

    def cleanup_retention(self) -> int:
        days = getattr(config, "RETENTION_DAYS", 30)
        if days <= 0:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        deleted = 0
        for folder in (self._mgr.storage_dir, self._mgr.toon_dir):
            try:
                for p in folder.glob("*"):
                    try:
                        if not p.is_file():
                            continue
                        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                        if mtime < cutoff:
                            p.unlink()
                            deleted += 1
                    except Exception:
                        continue
            except Exception:
                continue
        return deleted

    def consume_llm_request(self, daily_limit: int) -> int:
        if daily_limit <= 0:
            raise RateLimitExceededError("このアプリは現在リクエスト上限が0に設定されています。")

        today = date.today().isoformat()
        data = {}
        try:
            if self._rate_file.exists():
                data = json.loads(self._rate_file.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}

        count = int(data.get(today, 0) or 0)
        if count >= daily_limit:
            raise RateLimitExceededError(f"本日の上限（{daily_limit}回）に達しました。明日以降に再試行してください。")

        count += 1
        data[today] = count
        try:
            self._rate_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # 失敗しても最悪は上限が効かないだけ（ローカルフォールバック時のみ）
            logger.exception("ローカルレート制限ファイルの書き込みに失敗")
        return count

