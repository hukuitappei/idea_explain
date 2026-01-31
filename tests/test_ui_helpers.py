import pytest


class _SessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


class _Sidebar:
    def __init__(self):
        self.warnings = []

    def warning(self, msg):
        self.warnings.append(msg)

    def button(self, *args, **kwargs):
        return False


class _DummySt:
    def __init__(self, *, secrets=None):
        self.secrets = secrets or {}
        self.sidebar = _Sidebar()
        self.session_state = _SessionState()

    def error(self, *args, **kwargs):
        raise AssertionError("st.error called unexpectedly in this test")

    def stop(self):
        raise RuntimeError("st.stop called")


def test_resolve_user_key_or_stop_returns_anonymous_when_auth_disabled(monkeypatch):
    # ensure auth disabled
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    from core.ui.auth import resolve_user_key_or_stop

    st = _DummySt()
    assert resolve_user_key_or_stop(st) == "anonymous"


def test_init_history_store_sets_retention_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from core.ui.persistence import init_history_store

    st = _DummySt(secrets={})
    store = init_history_store(st, user_key="user@example.com")
    assert store is not None
    assert st.session_state.retention_cleanup_done is True


def test_consume_llm_quota_or_stop_allows_when_under_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from core.persistence.local_store import LocalHistoryStore
    from core.ui.rate_limit import consume_llm_quota_or_stop

    st = _DummySt()
    store = LocalHistoryStore(user_key="user@example.com")
    consume_llm_quota_or_stop(st, history_store=store, daily_limit=10)

