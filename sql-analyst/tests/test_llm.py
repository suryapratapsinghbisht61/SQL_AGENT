from unittest.mock import MagicMock

import pytest

from app import llm


class RateLimited(Exception):
    code = 429


@pytest.fixture
def fake_llm(monkeypatch):
    model = MagicMock()
    monkeypatch.setattr(llm, "get_llm", lambda: model)
    sleeps = []
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    return model, sleeps


def test_retries_on_429_then_succeeds(fake_llm):
    model, sleeps = fake_llm
    model.invoke.side_effect = [RateLimited("429 RESOURCE_EXHAUSTED"), MagicMock(text="ok")]
    assert llm.call_llm("hi") == "ok"
    assert model.invoke.call_count == 2
    assert sleeps  # backed off


def test_retries_on_503_overloaded(fake_llm):
    model, _ = fake_llm
    model.invoke.side_effect = [Exception("503 UNAVAILABLE. high demand"), MagicMock(text="ok")]
    assert llm.call_llm("hi") == "ok"


def test_gives_up_after_three_tries(fake_llm):
    model, _ = fake_llm
    model.invoke.side_effect = RateLimited("429")
    with pytest.raises(llm.LLMError, match="rate limited"):
        llm.call_llm("hi")
    assert model.invoke.call_count == 3


def test_other_errors_not_retried(fake_llm):
    model, _ = fake_llm
    model.invoke.side_effect = ValueError("bad key")
    with pytest.raises(llm.LLMError, match="bad key"):
        llm.call_llm("hi")
    assert model.invoke.call_count == 1


def test_min_delay_between_calls(fake_llm, monkeypatch):
    model, sleeps = fake_llm
    model.invoke.return_value = MagicMock(text="ok")
    llm.call_llm("a")
    llm.call_llm("b")
    assert sleeps and sleeps[-1] > 0
