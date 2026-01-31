import pytest

from core.schemas import Node, Edge, Flowchart


def _sample_flowchart(label_suffix: str = "") -> Flowchart:
    return Flowchart(
        nodes=[
            Node(id="start", label=f"開始{label_suffix}", type="start"),
            Node(id="process1", label="処理", type="process"),
            Node(id="node_end", label=f"終了{label_suffix}", type="end"),
        ],
        edges=[
            Edge(source="start", target="process1"),
            Edge(source="process1", target="node_end"),
        ],
    )


def test_user_key_to_dir_key_is_stable():
    from core.persistence.user_key import to_user_dir_key

    k1 = to_user_dir_key("User@Example.com")
    k2 = to_user_dir_key("user@example.com")
    assert k1 == k2
    assert len(k1) == 32
    assert all(c in "0123456789abcdef" for c in k1)


def test_local_history_store_roundtrip_and_rate_limit(tmp_path, monkeypatch):
    # Avoid writing into repo during tests
    monkeypatch.chdir(tmp_path)

    from core.persistence.local_store import LocalHistoryStore
    from core.persistence.types import RateLimitExceededError

    store = LocalHistoryStore(user_key="user@example.com")

    session_id = "s1"
    flow = _sample_flowchart()
    store.save_session(session_id, [flow])
    loaded = store.load_session(session_id)
    assert len(loaded) == 1
    assert loaded[0].nodes[0].id == "start"

    store.save_toon_file(session_id, flow)
    loaded_flow = store.load_toon_file(session_id)
    assert loaded_flow is not None
    assert loaded_flow.nodes[-1].id == "node_end"

    # rate limit
    assert store.consume_llm_request(2) == 1
    assert store.consume_llm_request(2) == 2
    with pytest.raises(RateLimitExceededError):
        store.consume_llm_request(2)

    assert store.delete_session(session_id) is True


def test_factory_falls_back_to_local_when_dsn_missing(monkeypatch):
    from core.persistence.factory import create_history_store

    # Force backend to postgres, but without DSN it must fall back
    monkeypatch.setenv("SESSION_STORE_BACKEND", "postgres")

    store = create_history_store(user_key="user@example.com", postgres_dsn="", retention_days=30)
    assert store.__class__.__name__ == "LocalHistoryStore"


def test_postgres_history_store_with_fake_psycopg(monkeypatch):
    """Covers PostgresHistoryStore logic without a real DB."""

    from core.persistence.postgres_store import PostgresHistoryStore
    from core.persistence.types import RateLimitExceededError

    class FakeState:
        def __init__(self):
            self.user_sessions = {}  # (user_key, session_id) -> dict
            self.usage = {}  # (user_key, day) -> count

    state = FakeState()

    class FakeCursor:
        def __init__(self, state: FakeState):
            self.state = state
            self._rows = []
            self.rowcount = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, params=()):
            q = " ".join(sql.strip().split()).lower()
            self._rows = []
            self.rowcount = 0

            if q.startswith("create table"):
                return

            if q.startswith("select session_id from user_sessions") and "toon_flow is not null" not in q:
                user_key = params[0]
                sessions = [sid for (uk, sid) in self.state.user_sessions.keys() if uk == user_key]
                self._rows = [(sid,) for sid in sessions]
                return

            if q.startswith("select session_id from user_sessions") and "toon_flow is not null" in q:
                user_key = params[0]
                sessions = []
                for (uk, sid), row in self.state.user_sessions.items():
                    if uk == user_key and row.get("toon_flow") is not None:
                        sessions.append(sid)
                self._rows = [(sid,) for sid in sessions]
                return

            if q.startswith("insert into user_sessions") and "history_json" in q:
                user_key, session_id, history_json = params
                # history_json is json string (due to _json_dump)
                import json

                self.state.user_sessions[(user_key, session_id)] = {
                    "history_json": json.loads(history_json),
                    "toon_flow": self.state.user_sessions.get((user_key, session_id), {}).get("toon_flow"),
                }
                return

            if q.startswith("insert into user_sessions") and "toon_flow" in q:
                user_key, session_id, toon_flow = params
                import json

                existing = self.state.user_sessions.get((user_key, session_id), {})
                self.state.user_sessions[(user_key, session_id)] = {
                    "history_json": existing.get("history_json", []),
                    "toon_flow": json.loads(toon_flow),
                }
                return

            if q.startswith("select history_json from user_sessions"):
                user_key, session_id = params
                row = self.state.user_sessions.get((user_key, session_id))
                self._rows = [(row.get("history_json"),)] if row else [(None,)]
                return

            if q.startswith("select toon_flow from user_sessions"):
                user_key, session_id = params
                row = self.state.user_sessions.get((user_key, session_id))
                self._rows = [(row.get("toon_flow"),)] if row else [(None,)]
                return

            if q.startswith("delete from user_sessions"):
                user_key, session_id = params
                existed = (user_key, session_id) in self.state.user_sessions
                if existed:
                    del self.state.user_sessions[(user_key, session_id)]
                    self.rowcount = 1
                else:
                    self.rowcount = 0
                return

            if q.startswith("insert into llm_daily_usage"):
                user_key, day, limit = params
                current = self.state.usage.get((user_key, day), 0)
                if current >= limit:
                    self._rows = []
                else:
                    current += 1
                    self.state.usage[(user_key, day)] = current
                    self._rows = [(current,)]
                return

            if q.startswith("delete from llm_daily_usage"):
                return

            if q.startswith("delete from user_sessions") and "updated_at" in q:
                self.rowcount = 0
                return

            raise AssertionError(f"Unhandled SQL: {sql}")

        def fetchall(self):
            return list(self._rows)

        def fetchone(self):
            return self._rows[0] if self._rows else None

    class FakeConn:
        def __init__(self, state: FakeState):
            self.state = state

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor(self.state)

        def commit(self):
            return None

    # Patch _connect to use our fake DB
    monkeypatch.setattr(PostgresHistoryStore, "_connect", lambda self: FakeConn(state))

    store = PostgresHistoryStore(dsn="fake", user_key="user@example.com", retention_days=30)
    session_id = "s1"

    flow = _sample_flowchart()
    store.save_session(session_id, [flow])
    loaded = store.load_session(session_id)
    assert len(loaded) == 1

    store.save_toon_file(session_id, flow)
    loaded_flow = store.load_toon_file(session_id)
    assert loaded_flow is not None

    appended = store.append_toon_log(session_id, _sample_flowchart(label_suffix="X"))
    assert appended is not None

    assert store.consume_llm_request(2) == 1
    assert store.consume_llm_request(2) == 2
    with pytest.raises(RateLimitExceededError):
        store.consume_llm_request(2)

    assert store.delete_session(session_id) is True


def test_postgres_connect_retries_with_ipv4_hostaddr(monkeypatch):
    """Ensure IPv4 fallback is attempted on IPv6 connect errors."""

    from core.persistence.postgres_store import PostgresHistoryStore

    calls: list[str] = []

    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakePsycopg:
        @staticmethod
        def connect(conninfo: str):
            calls.append(conninfo)
            if len(calls) == 1:
                raise Exception(
                    'connection to server at "2406:da18:243:7426:f70d:bac5:9683:92a6", port 5432 failed: Cannot assign requested address'
                )
            return DummyConn()

    # Inject fake psycopg module used in _connect()
    import sys

    sys.modules["psycopg"] = FakePsycopg  # type: ignore[assignment]

    # Avoid real DNS; return a deterministic IPv4
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", port))],
    )

    store = PostgresHistoryStore.__new__(PostgresHistoryStore)
    store.dsn = "postgresql://postgres:pw@db.example.com:5432/postgres?sslmode=require"

    conn = store._connect()
    assert conn is not None
    assert len(calls) == 2
    assert "hostaddr=1.2.3.4" in calls[1]

