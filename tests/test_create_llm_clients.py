from __future__ import annotations

import pytest

from compendiumscribe.create_llm_clients import create_openai_client


def test_create_openai_client_requires_responses_support(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **_kwargs):
            pass

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "compendiumscribe.create_llm_clients.load_dotenv",
        lambda: None,
    )
    monkeypatch.setattr(
        "compendiumscribe.create_llm_clients.OpenAI",
        DummyOpenAI,
    )

    with pytest.raises(RuntimeError) as exc_info:
        create_openai_client()

    assert "Responses API" in str(exc_info.value)


def test_create_openai_client_returns_native_client(monkeypatch):
    instances: list[object] = []

    class DummyResponses:
        pass

    class DummyOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.responses = DummyResponses()
            instances.append(self)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "compendiumscribe.create_llm_clients.load_dotenv",
        lambda: None,
    )
    monkeypatch.setattr(
        "compendiumscribe.create_llm_clients.OpenAI",
        DummyOpenAI,
    )

    client = create_openai_client(timeout=123)

    assert client is instances[0]
    assert isinstance(client.responses, DummyResponses)
    assert instances[0].kwargs["timeout"] == 123
