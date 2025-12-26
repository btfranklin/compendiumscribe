from __future__ import annotations

from .config import ResearchConfig
from .errors import (
    DeepResearchError,
    ResearchTimeoutError,
)
from .execution import (
    await_completion,
    execute_deep_research,
)
from .orchestrator import build_compendium
from .parsing import (
    collect_response_text,
    decode_json_payload,
    parse_deep_research_response,
)
from .planning import (
    compose_deep_research_prompt,
    default_research_plan,
    generate_research_plan,
    load_prompt_template,
)
from .progress import (
    ProgressPhase,
    ProgressStatus,
    ResearchProgress,
    emit_progress,
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
    "ResearchTimeoutError",
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
    "collect_response_text",
    "decode_json_payload",
    "parse_deep_research_response",
    "execute_deep_research",
    "await_completion",
    "ACTION_SUMMARY_KEYS",
    "coerce_optional_string",
    "first_non_empty",
    "get_field",
    "normalize_response_snapshot",
    "simplify_action_snapshot",
    "stringify_metadata_value",
    "truncate_text",
]
