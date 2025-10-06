from __future__ import annotations

from types import SimpleNamespace

import pytest

from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.errors import DeepResearchError
from compendiumscribe.research.execution import execute_deep_research


class StubStream:
    def __init__(self, events, final_response=None):
        self._events = list(events)
        self._final_response = final_response
        self.get_final_response_called = False

    def __iter__(self):
        for event in self._events:
            yield event

    def get_final_response(self):
        self.get_final_response_called = True
        return self._final_response


def test_execute_deep_research_requires_data_source():
    config = ResearchConfig(
        use_web_search=False,
        enable_code_interpreter=False,
        stream_progress=False,
    )

    with pytest.raises(DeepResearchError):
        execute_deep_research(SimpleNamespace(), "prompt", config)


def test_execute_deep_research_streaming_returns_final_response():
    progress_updates = []

    def callback(update):
        progress_updates.append((update.phase, update.status, update.message))

    final_response = SimpleNamespace(
        id="resp_123",
        status="completed",
        output_text='{"result": "ok"}',
        output=[],
    )

    events = [
        SimpleNamespace(type="response.created"),
        SimpleNamespace(
            type="response.output_item.added",
            item={
                "type": "web_search_call",
                "id": "ws_1",
                "status": "completed",
                "action": {
                    "type": "search",
                    "query": "double bubble bath",
                },
            },
        ),
        SimpleNamespace(type="response.completed", response=final_response),
    ]

    class StubResponses:
        def __init__(self):
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return StubStream(events, final_response)

    responses = StubResponses()
    client = SimpleNamespace(responses=responses)

    config = ResearchConfig(stream_progress=True, progress_callback=callback)

    response = execute_deep_research(client, "prompt", config)

    assert response is final_response
    assert responses.calls
    call_kwargs = responses.calls[0]
    assert call_kwargs["stream"] is True
    assert call_kwargs["background"] is False
    assert any(
        phase == "trace" and "Exploring sources" in message
        for phase, _status, message in progress_updates
    )


def test_execute_deep_research_streaming_raises_on_error():
    events = [
        SimpleNamespace(type="response.created"),
        SimpleNamespace(
            type="response.failed",
            error={"message": "rate limited"},
        ),
    ]

    class StubResponses:
        def create(self, **kwargs):
            return StubStream(events)

    client = SimpleNamespace(responses=StubResponses())
    config = ResearchConfig(stream_progress=True)

    with pytest.raises(DeepResearchError, match="rate limited"):
        execute_deep_research(client, "prompt", config)
