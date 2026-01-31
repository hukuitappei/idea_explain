import pytest
import requests

from core import config
from core.llm_client import LLMClient
from core.schemas import Node, Edge, Flowchart


class DummyResponse:
    def __init__(self, content: str, status_code: int = 200, error: str | None = None):
        self._content = content
        self.status_code = status_code
        self._error = error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError("http error")

    def json(self):
        if self.status_code >= 400:
            return {"error": self._error or "error"}
        return {"message": {"content": self._content}}


def test_is_question_response():
    assert LLMClient.is_question_response("以下の情報を教えてください：1. 〜") is True
    assert LLMClient.is_question_response("[Node]\nid: a") is False


def test_validate_output_size_limits():
    client = LLMClient()
    ok, _ = client.validate_output_size("[Node]\n" * config.MAX_TOON_NODES)
    assert ok is True

    too_many = ("[Node]\n" * (config.MAX_TOON_NODES + 1)) + ("[Edge]\n" * (config.MAX_TOON_EDGES + 1))
    ok2, msg = client.validate_output_size(too_many)
    assert ok2 is False
    assert "上限" in msg


def test_generate_flow_success(monkeypatch):
    def fake_post(*args, **kwargs):
        return DummyResponse("[Node]\nid: a\nlabel: A\n")

    monkeypatch.setattr("core.llm_client.requests.post", fake_post)
    client = LLMClient()
    out = client.generate_flow("テスト入力")
    assert "[Node]" in out


def test_generate_flow_timeout_raises_llmapierror(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.exceptions.Timeout("timeout")

    monkeypatch.setattr("core.llm_client.requests.post", fake_post)
    client = LLMClient()
    with pytest.raises(Exception):
        client.generate_flow("テスト入力")


def test_generate_partial_change_success(monkeypatch):
    def fake_post(*args, **kwargs):
        return DummyResponse("[Node]\nid: a\nlabel: A\n")

    monkeypatch.setattr("core.llm_client.requests.post", fake_post)

    target = Flowchart(
        nodes=[
            Node(id="start", label="開始", type="start"),
            Node(id="a", label="A", type="process"),
            Node(id="node_end", label="終了", type="end"),
        ],
        edges=[Edge(source="start", target="a"), Edge(source="a", target="node_end")],
        subgraphs=None,
    )
    full = Flowchart(
        nodes=[Node(id="start", label="開始", type="start"), Node(id="a", label="A", type="process"), Node(id="node_end", label="終了", type="end")],
        edges=[Edge(source="start", target="a"), Edge(source="a", target="node_end")],
        subgraphs=None,
    )

    client = LLMClient()
    out = client.generate_partial_change("変更して", target, full)
    assert "[Node]" in out


def test_generate_flow_openai_backend_success(monkeypatch):
    # Force OpenAI backend
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")

    class OpenAIResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "[Node]\nid: a\nlabel: A\n"}}]}

    def fake_post(*args, **kwargs):
        return OpenAIResponse()

    monkeypatch.setattr("core.llm_client.requests.post", fake_post)

    client = LLMClient()
    out = client.generate_flow("テスト入力")
    assert "[Node]" in out

