from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING
import os

from dotenv import load_dotenv

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from .progress import ResearchProgress


@dataclass
class ResearchConfig:
    """Configuration flags for the deep research pipeline."""

    deep_research_model: str = field(
        default_factory=lambda: _default_deep_research_model()
    )
    prompt_refiner_model: str = "gpt-4.1"
    use_prompt_refinement: bool = True
    background: bool = True
    poll_interval_seconds: float = 5.0
    max_poll_attempts: int = 240
    enable_code_interpreter: bool = True
    use_web_search: bool = True
    max_tool_calls: int | None = None
    request_timeout_seconds: int = 3600
    progress_callback: Callable[["ResearchProgress"], None] | None = None


def _default_deep_research_model() -> str:
    load_dotenv()
    env_value = os.getenv("RESEARCH_MODEL")
    if env_value:
        stripped = env_value.strip()
        if stripped:
            return stripped
    return "o3-deep-research"


__all__ = ["ResearchConfig", "_default_deep_research_model"]
