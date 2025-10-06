from __future__ import annotations

from compendiumscribe.research.execution.stream_events import (
    extract_stream_error_message,
    merge_action_payload,
    merge_response_payload,
)


def test_merge_action_payload_appends_delta_and_merges_nested_dicts():
    existing = {"query": "double", "metadata": {"page": 1}}
    incoming = {
        "query_delta": " bubble",
        "metadata": {"page": 2, "filters": ["science"]},
    }

    result = merge_action_payload(existing, incoming)

    assert result["query"] == "double bubble"
    assert result["metadata"] == {"page": 2, "filters": ["science"]}


def test_merge_response_payload_combines_nested_structure():
    existing = {"headers": {"x-rate-limit": "10"}, "body": "ok"}
    incoming = {
        "headers": {"x-rate-limit-remaining": "9"},
        "body": "done",
        "status": 200,
    }

    result = merge_response_payload(existing, incoming)

    assert result["headers"] == {
        "x-rate-limit": "10",
        "x-rate-limit-remaining": "9",
    }
    assert result["body"] == "done"
    assert result["status"] == 200


def test_extract_stream_error_message_handles_dict_payload():
    event = {"error": {"code": "rate_limited"}}

    message = extract_stream_error_message(event)

    assert message == "rate_limited"
