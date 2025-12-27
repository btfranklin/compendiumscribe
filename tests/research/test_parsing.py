from __future__ import annotations

from types import SimpleNamespace

import pytest

from compendiumscribe.research.parsing import (
    collect_response_text,
    decode_json_payload,
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


def test_collect_response_text_handles_nested_fragments():
    response = SimpleNamespace(
        output=[
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": [
                            {
                                "type": "text",
                                "text": "{\n  \"key\": \"value\"\n}",
                            }
                        ],
                    }
                ],
            }
        ]
    )

    collected = collect_response_text(response)

    assert collected == '{\n  "key": "value"\n}'


def test_collect_response_text_handles_output_text_object():
    response = SimpleNamespace(
        output_text={
            "type": "output_text",
            "text": [
                {
                    "type": "text",
                    "text": "{\"foo\": 1}",
                }
            ],
        },
        output=[],
    )

    collected = collect_response_text(response)

    assert collected == '{"foo": 1}'
