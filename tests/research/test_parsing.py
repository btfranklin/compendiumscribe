from __future__ import annotations

from types import SimpleNamespace

import pytest

from compendiumscribe.research.parsing import (
    decode_json_payload,
    extract_trace_events,
)


@pytest.mark.parametrize(
    "payload",
    [
        '{"key": "value"}',
        "```json\n{\n  \"key\": \"value\"\n}\n```",
        "noise before {\"key\": \"value\"} noise after",
    ],
)
def test_decode_json_payload_handles_wrappers(payload):
    result = decode_json_payload(payload)

    assert result == {"key": "value"}


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

    trace = extract_trace_events(response)

    assert trace == [
        {
            "id": "ws_1",
            "type": "web_search_call",
            "status": "completed",
            "action": {"query": "test"},
            "response": None,
        }
    ]
