from __future__ import annotations

from compendiumscribe.research.trace import (
    summaries_from_trace_events,
    summarize_trace_event,
)


def test_summarize_trace_event_includes_query_excerpt():
    event = {
        "id": "call_1",
        "type": "web_search_call",
        "status": "completed",
        "action": {"type": "search", "query": "example query text"},
    }

    message = summarize_trace_event(event)

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

    summaries = summaries_from_trace_events(events, seen_tokens=set())

    assert any(
        "Exploring sources" in item["message"] for item in summaries
    )
    assert any(
        "code interpreter" in item["message"] for item in summaries
    )
