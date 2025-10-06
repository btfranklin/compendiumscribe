from __future__ import annotations

from .config import ResearchConfig
from .errors import DeepResearchError
from .execution import (
    await_completion,
    execute_deep_research,
)
from .orchestrator import build_compendium
from .parsing import (
    collect_response_text,
    decode_json_payload,
    extract_trace_events,
    parse_deep_research_response,
)
from .planning import (
    compose_deep_research_prompt,
    default_research_plan,
    generate_research_plan,
    load_prompt_template,
    strip_leading_markdown_header,
)
from .progress import (
    ProgressPhase,
    ProgressStatus,
    ResearchProgress,
    emit_progress,
)
from .trace import (
    format_query_list,
    iter_trace_progress_events,
    summaries_from_trace_events,
    summarize_trace_event,
    trace_event_from_item,
    trace_event_token,
)
from .utils import (
    ACTION_SUMMARY_KEYS,
    coerce_optional_string,
    first_non_empty,
    get_field,
    normalize_response_snapshot,
    simplify_action_snapshot,
    stringify_metadata_value,
    truncate_text,
)

__all__ = [
    "DeepResearchError",
    "ResearchConfig",
    "ProgressPhase",
    "ProgressStatus",
    "ResearchProgress",
    "emit_progress",
    "build_compendium",
    "compose_deep_research_prompt",
    "default_research_plan",
    "generate_research_plan",
    "load_prompt_template",
    "strip_leading_markdown_header",
    "collect_response_text",
    "decode_json_payload",
    "extract_trace_events",
    "parse_deep_research_response",
    "execute_deep_research",
    "await_completion",
    "summaries_from_trace_events",
    "summarize_trace_event",
    "trace_event_from_item",
    "format_query_list",
    "trace_event_token",
    "iter_trace_progress_events",
    "ACTION_SUMMARY_KEYS",
    "coerce_optional_string",
    "first_non_empty",
    "get_field",
    "normalize_response_snapshot",
    "simplify_action_snapshot",
    "stringify_metadata_value",
    "truncate_text",
]
