from types import SimpleNamespace

import pytest

from compendiumscribe.research_domain import (
    DeepResearchError,
    ResearchConfig,
    _compose_deep_research_prompt,
    _decode_json_payload,
    _execute_deep_research,
    _extract_trace_events,
    _strip_leading_markdown_header,
)


def test_strip_leading_markdown_header_removes_heading():
    prompt = """# Title\n\n## Subtitle\n\nDo things."""
    assert _strip_leading_markdown_header(prompt).startswith("## Subtitle")


def test_compose_deep_research_prompt_uses_plan_details():
    plan = {
        "primary_objective": "Understand the domain",
        "audience": "Analysts",
        "key_sections": [{"title": "Foundations", "focus": "History"}],
        "research_questions": ["What started the field?"],
        "methodology_preferences": ["Prioritise peer-reviewed sources."],
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
        vector_store_ids=(),
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
