from types import SimpleNamespace

import pytest

from compendiumscribe.create_llm_clients import (
    MissingAPIKeyError,
    create_openai_client,
)


class DummyOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_create_openai_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "compendiumscribe.create_llm_clients.load_dotenv",
        lambda: None,
    )
    monkeypatch.setattr(
        "compendiumscribe.create_llm_clients.OpenAI",
        DummyOpenAI,
    )

    with pytest.raises(MissingAPIKeyError):
        create_openai_client()


def test_create_openai_client_uses_timeout(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "compendiumscribe.create_llm_clients.OpenAI",
        fake_openai,
    )

    client = create_openai_client(timeout=123)

    assert captured["api_key"] == "sk-test"
    assert captured["timeout"] == 123
    assert client.api_key == "sk-test"
