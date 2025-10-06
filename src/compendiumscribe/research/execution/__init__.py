from __future__ import annotations

from .core import execute_deep_research
from .polling import await_completion
from .stream_events import (
    accumulate_stream_tool_event,
    collect_stream_fragments,
    emit_trace_updates_from_item,
    extract_stream_error_message,
    extract_stream_tool_fragment,
    merge_action_payload,
    merge_response_payload,
    merge_tool_fragment,
)
from .streaming import execute_deep_research_streaming, handle_stream_event


__all__ = [
    "accumulate_stream_tool_event",
    "await_completion",
    "collect_stream_fragments",
    "emit_trace_updates_from_item",
    "execute_deep_research",
    "execute_deep_research_streaming",
    "extract_stream_error_message",
    "extract_stream_tool_fragment",
    "handle_stream_event",
    "merge_action_payload",
    "merge_response_payload",
    "merge_tool_fragment",
]
