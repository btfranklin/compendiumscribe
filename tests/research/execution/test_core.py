from __future__ import annotations

from types import SimpleNamespace

import pytest

from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.errors import DeepResearchError
from compendiumscribe.research.execution import execute_deep_research


def test_execute_deep_research_requires_data_source():
    config = ResearchConfig(
        use_web_search=False,
        enable_code_interpreter=False,
    )

    with pytest.raises(DeepResearchError):
        execute_deep_research(SimpleNamespace(), "prompt", config)


def test_execute_deep_research_returns_completed_response():
    progress_updates: list[tuple[str, str, str]] = []

    def callback(update):
        progress_updates.append(
            (update.phase, update.status, update.message)
        )

    final_response = SimpleNamespace(
        id="resp_completed",
        status="completed",
        output=[],
    )

    class StubResponses:
        def __init__(self):
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return final_response

    responses = StubResponses()
    client = SimpleNamespace(responses=responses)

    config = ResearchConfig(
        background=False,
        progress_callback=callback,
    )

    result = execute_deep_research(client, "prompt", config)

    assert result is final_response
    assert responses.calls
    payload = responses.calls[0]
    assert payload["background"] is False
    assert (
        "deep_research",
        "starting",
        "Submitting deep research request to OpenAI.",
    ) in progress_updates
    assert (
        "deep_research",
        "completed",
        "Deep research completed synchronously.",
    ) in progress_updates


def test_execute_deep_research_polls_until_complete():
    progress_updates: list[tuple[str, str, str]] = []

    def callback(update):
        progress_updates.append(
            (update.phase, update.status, update.message)
        )

    pending = SimpleNamespace(
        id="resp_poll",
        status="in_progress",
        output=[],
    )
    final_response = SimpleNamespace(
        id="resp_poll",
        status="completed",
        output=[],
    )

    class PollingResponses:
        def __init__(self):
            self.create_calls: list[dict[str, object]] = []
            self.retrieve_calls: list[str] = []

        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            return pending

        def retrieve(self, response_id: str):
            self.retrieve_calls.append(response_id)
            return final_response

    responses = PollingResponses()
    client = SimpleNamespace(responses=responses)

    config = ResearchConfig(
        background=True,
        polling_interval_seconds=0,
        max_poll_time_minutes=1,
        progress_callback=callback,
    )

    result = execute_deep_research(client, "prompt", config)

    assert result is final_response
    assert responses.retrieve_calls == ["resp_poll"]
    assert (
        "deep_research",
        "in_progress",
        "Polling for deep research completion.",
    ) in progress_updates
    assert (
        "deep_research",
        "completed",
        "Deep research run finished; decoding payload.",
    ) in progress_updates


def test_execute_deep_research_raises_timeout_error():
    pending = SimpleNamespace(
        id="resp_poll",
        status="in_progress",
        output=[],
    )

    class FastPollingResponses:
        def create(self, **kwargs):
            return pending

        def retrieve(self, response_id: str):
            return pending

    responses = FastPollingResponses()
    client = SimpleNamespace(responses=responses)

    # Set a very short timeout and interval
    config = ResearchConfig(
        background=True,
        polling_interval_seconds=0.01,
        max_poll_time_minutes=0.0001,  # Fraction of a second
    )

    from compendiumscribe.research.errors import ResearchTimeoutError
    with pytest.raises(ResearchTimeoutError) as excinfo:
        execute_deep_research(client, "prompt", config)
    
    assert excinfo.value.research_id == "resp_poll"
