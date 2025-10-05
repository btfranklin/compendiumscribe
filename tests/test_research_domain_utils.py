from types import SimpleNamespace

import pytest

from compendiumscribe.research_domain import (
    DeepResearchError,
    ResearchConfig,
    _compose_deep_research_prompt,
    _decode_json_payload,
    _execute_deep_research,
    _extract_trace_events,
    _summaries_from_trace_events,
    _summarize_trace_event,
    _strip_leading_markdown_header,
)


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


def test_strip_leading_markdown_header_removes_heading():
    prompt = """# Title\n\n## Subtitle\n\nDo things."""
    assert _strip_leading_markdown_header(prompt).startswith("## Subtitle")


def test_research_config_uses_env_override(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "custom-deep-model")

    config = ResearchConfig()

    assert config.deep_research_model == "custom-deep-model"


def test_compose_deep_research_prompt_uses_plan_details():
    plan = {
        "primary_objective": "Understand the domain",
        "audience": "Analysts",
        "key_sections": [{"title": "Foundations", "focus": "History"}],
        "research_questions": ["What started the field?"],
        "methodology_preferences": ["Prioritize peer-reviewed sources."],
    }

    prompt = _compose_deep_research_prompt("Sample Topic", plan)

    assert "Sample Topic" in prompt
    assert "Foundations" in prompt
    assert "What started the field?" in prompt
    assert "schema" in prompt
    assert not prompt.lstrip().startswith("#")


@pytest.mark.parametrize(
    "payload",
    [
        '{"key": "value"}',
        "```json\n{\n  \"key\": \"value\"\n}\n```",
        "noise before {\"key\": \"value\"} noise after",
    ],
)
def test_decode_json_payload_handles_wrappers(payload):
    result = _decode_json_payload(payload)
    assert result == {"key": "value"}


def test_execute_deep_research_requires_data_source():
    config = ResearchConfig(
        use_web_search=False,
        enable_code_interpreter=False,
        stream_progress=False,
    )

    with pytest.raises(DeepResearchError):
        _execute_deep_research(SimpleNamespace(), "prompt", config)


def test_extract_trace_events_collects_tool_calls():
    response = SimpleNamespace(
        output=[
            {
                "type": "web_search_call",
                "id": "ws_1",
                "status": "completed",
                "action": {"query": "test"},
            },
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "{}"}],
            },
        ]
    )

    trace = _extract_trace_events(response)

    assert trace == [
        {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "completed",
            "action": {"query": "test"},
            "response": None,
        }
    ]


def test_summarize_trace_event_includes_query_excerpt():
    event = {
        "id": "call_1",
        "type": "web_search_call",
        "status": "completed",
        "action": {"type": "search", "query": "example query text"},
    }

    message = _summarize_trace_event(event)

    assert "search" in message
    assert "example query text" in message


def test_summaries_from_trace_events_groups_queries():
    events = [
        {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "completed",
            "action": {
                "type": "search",
                "query": "Flute history 19th century",
            },
        },
        {
            "id": "ws_2",
            "type": "web_search_call",
            "status": "completed",
            "action": {
                "type": "search",
                "query": "Ancient Egyptian flutes",
            },
        },
        {
            "id": "cp_1",
            "type": "code_interpreter_call",
            "status": "completed",
            "action": {"type": "code"},
        },
    ]

    summaries = _summaries_from_trace_events(events, seen_tokens=set())

    assert any(
        "Exploring sources" in item["message"] for item in summaries
    )
    assert any(
        "code interpreter" in item["message"] for item in summaries
    )


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

    response = _execute_deep_research(client, "prompt", config)

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
        _execute_deep_research(client, "prompt", config)
