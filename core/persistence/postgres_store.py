from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from core import config
from core.logging_config import logger
from core.schemas import Edge, Flowchart, Node

from .types import HistoryStore, RateLimitExceededError


class PostgresHistoryStore(HistoryStore):
    """Postgres-backed persistence (suitable for Supabase).

    Schema is created automatically (CREATE TABLE IF NOT EXISTS).
    Data stored is minimal: Flowchart/TOON only (no raw prompts).
    """

    def __init__(self, *, dsn: str, user_key: str, retention_days: int):
        self.dsn = (dsn or "").strip()
        if not self.dsn:
            raise ValueError("Postgres DSN が空です")
        self.user_key = (user_key or "").strip().lower()
        if not self.user_key:
            raise ValueError("user_key が空です")
        self.retention_days = retention_days

        self._ensure_schema()

    # ---- Internal helpers ----

    def _connect(self):
        import psycopg  # available in dev env; required in production

        # autocommit off; we commit explicitly
        return psycopg.connect(self.dsn)

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS user_sessions (
                          user_key   TEXT NOT NULL,
                          session_id TEXT NOT NULL,
                          history_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                          toon_flow  JSONB,
                          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                          PRIMARY KEY (user_key, session_id)
                        );
                        """
                    )
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS llm_daily_usage (
                          user_key   TEXT NOT NULL,
                          day        DATE NOT NULL,
                          count      INT NOT NULL DEFAULT 0,
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                          PRIMARY KEY (user_key, day)
                        );
                        """
                    )
                conn.commit()
        except Exception:
            logger.exception("Postgres schema init failed")
            raise

    def _validate_session_id(self, session_id: str) -> str:
        if not session_id:
            raise ValueError("セッション名が空です")
        if not config.SESSION_ID_PATTERN.match(session_id):
            raise ValueError("無効なセッション名です（英数字、ハイフン、アンダースコアのみ / 1-255文字）")
        return session_id

    # ---- HistoryStore API ----

    def list_sessions(self) -> List[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id FROM user_sessions WHERE user_key = %s ORDER BY updated_at DESC",
                    (self.user_key,),
                )
                return [row[0] for row in cur.fetchall()]

    def save_session(self, session_id: str, history: List[Flowchart]) -> None:
        session_id = self._validate_session_id(session_id)
        payload = [flow.model_dump(mode="json") for flow in (history or [])]
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_sessions (user_key, session_id, history_json, updated_at)
                    VALUES (%s, %s, %s::jsonb, now())
                    ON CONFLICT (user_key, session_id)
                    DO UPDATE SET history_json = EXCLUDED.history_json, updated_at = now()
                    """,
                    (self.user_key, session_id, _json_dump(payload)),
                )
            conn.commit()

    def load_session(self, session_id: str) -> List[Flowchart]:
        session_id = self._validate_session_id(session_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT history_json FROM user_sessions WHERE user_key=%s AND session_id=%s",
                    (self.user_key, session_id),
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    return []
                data = row[0] or []
                if isinstance(data, str):
                    import json

                    data = json.loads(data) if data.strip() else []

        flowcharts: List[Flowchart] = []
        for item in data:
            try:
                flowcharts.append(Flowchart(**_normalize_flowchart_dict(item)))
            except Exception:
                continue
        return flowcharts

    def delete_session(self, session_id: str) -> bool:
        session_id = self._validate_session_id(session_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_sessions WHERE user_key=%s AND session_id=%s",
                    (self.user_key, session_id),
                )
                deleted = cur.rowcount or 0
            conn.commit()
        return deleted > 0

    def list_toon_files(self) -> List[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id FROM user_sessions WHERE user_key=%s AND toon_flow IS NOT NULL ORDER BY updated_at DESC",
                    (self.user_key,),
                )
                return [row[0] for row in cur.fetchall()]

    def save_toon_file(self, session_id: str, flowchart: Flowchart) -> None:
        session_id = self._validate_session_id(session_id)
        payload = flowchart.model_dump(mode="json")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_sessions (user_key, session_id, toon_flow, updated_at)
                    VALUES (%s, %s, %s::jsonb, now())
                    ON CONFLICT (user_key, session_id)
                    DO UPDATE SET toon_flow = EXCLUDED.toon_flow, updated_at = now()
                    """,
                    (self.user_key, session_id, _json_dump(payload)),
                )
            conn.commit()

    def load_toon_file(self, session_id: str) -> Optional[Flowchart]:
        session_id = self._validate_session_id(session_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT toon_flow FROM user_sessions WHERE user_key=%s AND session_id=%s",
                    (self.user_key, session_id),
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    return None
                data = row[0]
                if isinstance(data, str):
                    import json

                    data = json.loads(data) if data.strip() else None
        try:
            return Flowchart(**_normalize_flowchart_dict(data))
        except Exception:
            return None

    def append_toon_log(self, session_id: str, new_flowchart: Flowchart) -> Flowchart:
        session_id = self._validate_session_id(session_id)
        existing = self.load_toon_file(session_id)
        if existing is None:
            # new file
            self.save_toon_file(session_id, new_flowchart)
            return new_flowchart

        merged = _merge_flowcharts(existing, new_flowchart)
        merged = merged.apply_logic_gap_detection()
        self.save_toon_file(session_id, merged)
        return merged

    def cleanup_retention(self) -> int:
        days = int(self.retention_days or 0)
        if days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    # Global retention (not per-user). Public operation requires data expiration even if user never returns.
                    "DELETE FROM user_sessions WHERE updated_at < %s",
                    (cutoff,),
                )
                deleted = cur.rowcount or 0
                # keep rate limit table small (retain ~40 days)
                cur.execute(
                    "DELETE FROM llm_daily_usage WHERE day < %s",
                    (date.today() - timedelta(days=40),),
                )
            conn.commit()
        return int(deleted)

    def consume_llm_request(self, daily_limit: int) -> int:
        if daily_limit <= 0:
            raise RateLimitExceededError("このアプリは現在リクエスト上限が0に設定されています。")
        today = date.today()

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_daily_usage (user_key, day, count, updated_at)
                    VALUES (%s, %s, 1, now())
                    ON CONFLICT (user_key, day)
                    DO UPDATE
                      SET count = llm_daily_usage.count + 1,
                          updated_at = now()
                      WHERE llm_daily_usage.count < %s
                    RETURNING count
                    """,
                    (self.user_key, today, int(daily_limit)),
                )
                row = cur.fetchone()
            conn.commit()

        if not row:
            raise RateLimitExceededError(f"本日の上限（{daily_limit}回）に達しました。明日以降に再試行してください。")
        return int(row[0])


def _json_dump(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


def _normalize_flowchart_dict(item: dict) -> dict:
    """Normalize legacy/enum variants to current pydantic-friendly dict."""
    if not isinstance(item, dict):
        return {}
    if "nodes" in item and isinstance(item["nodes"], list):
        for node in item["nodes"]:
            if isinstance(node, dict) and "status" in node:
                st = node["status"]
                if isinstance(st, dict) and "value" in st:
                    node["status"] = st["value"]
                elif st is None or st == "":
                    node["status"] = "active"
    return item


def _merge_flowcharts(existing_flow: Flowchart, new_flowchart: Flowchart) -> Flowchart:
    """Same merge behavior as HistoryManager.append_toon_log()."""
    existing_nodes_map = {node.id: node for node in existing_flow.nodes}

    merged_nodes: list[Node] = []
    processed_ids: set[str] = set()

    for existing_node in existing_flow.nodes:
        new_node = next((n for n in new_flowchart.nodes if n.id == existing_node.id), None)
        if new_node:
            merged_nodes.append(new_node)
            processed_ids.add(new_node.id)
        else:
            merged_nodes.append(existing_node)
            processed_ids.add(existing_node.id)

    for new_node in new_flowchart.nodes:
        if new_node.id not in processed_ids:
            merged_nodes.append(new_node)

    existing_edges_map = {(edge.source, edge.target): edge for edge in existing_flow.edges}
    merged_edges: list[Edge] = []
    processed_edge_keys: set[tuple[str, str]] = set()

    for existing_edge in existing_flow.edges:
        edge_key = (existing_edge.source, existing_edge.target)
        new_edge = next((e for e in new_flowchart.edges if (e.source, e.target) == edge_key), None)
        if new_edge:
            merged_edges.append(new_edge)
            processed_edge_keys.add(edge_key)
        else:
            merged_edges.append(existing_edge)
            processed_edge_keys.add(edge_key)

    for new_edge in new_flowchart.edges:
        edge_key = (new_edge.source, new_edge.target)
        if edge_key not in processed_edge_keys:
            merged_edges.append(new_edge)

    merged_subgraphs = None
    if existing_flow.subgraphs or new_flowchart.subgraphs:
        merged_subgraphs = {}
        if existing_flow.subgraphs:
            merged_subgraphs.update(existing_flow.subgraphs)
        if new_flowchart.subgraphs:
            merged_subgraphs.update(new_flowchart.subgraphs)

    return Flowchart(nodes=merged_nodes, edges=merged_edges, subgraphs=merged_subgraphs)

