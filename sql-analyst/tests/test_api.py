from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import main
from app.llm import LLMError


@pytest.fixture
def client(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(main, "build_graph", lambda: fake)
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c, fake


def test_health(client):
    c, _ = client
    assert c.get("/health").json() == {"status": "ok"}


def test_chat_page(client):
    c, _ = client
    r = c.get("/")
    assert r.status_code == 200 and "SQL Analyst" in r.text


def test_ask(client):
    c, fake = client
    fake.invoke.return_value = {
        "question": "How many artists?", "sql": "SELECT count(*) AS n FROM artist",
        "rows": [{"n": 275}], "attempts": 1, "error": None, "answer": "There are 275 artists.",
    }
    r = c.post("/ask", json={"question": "  How many artists?  "})
    assert r.status_code == 200
    assert r.json() == {
        "answer": "There are 275 artists.", "sql": "SELECT count(*) AS n FROM artist",
        "rows": [{"n": 275}], "attempts": 1, "error": None,
    }
    fake.invoke.assert_called_once_with({"question": "How many artists?"})


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "   "}, {"question": "x" * 501}, {"question": 5}])
def test_invalid_input_422(client, body):
    c, _ = client
    assert c.post("/ask", json=body).status_code == 422


def test_llm_error_is_clean_json(client):
    c, fake = client
    fake.invoke.side_effect = LLMError("LLM rate limit still exceeded after 3 tries")
    r = c.post("/ask", json={"question": "q"})
    assert r.status_code == 503 and "rate limit" in r.json()["detail"]


def test_unexpected_error_hides_trace(client):
    c, fake = client
    fake.invoke.side_effect = RuntimeError("secret internals")
    r = c.post("/ask", json={"question": "q"})
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error"}
