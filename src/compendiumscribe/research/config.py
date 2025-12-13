from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING
import os

from dotenv import load_dotenv

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from .progress import ResearchProgress

from .errors import MissingConfigurationError


@dataclass
class ResearchConfig:
    """Configuration flags for the deep research pipeline."""

    deep_research_model: str = field(
        default_factory=lambda: _default_deep_research_model()
    )
    prompt_refiner_model: str = field(
        default_factory=lambda: _default_prompt_refiner_model()
    )
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
    # Check specific env var first, then fallback to generic
    model = os.getenv("DEEP_RESEARCH_MODEL") or os.getenv("RESEARCH_MODEL")
    if not model:
        raise MissingConfigurationError(
            "DEEP_RESEARCH_MODEL must be set in environment."
        )
    return model


def _default_prompt_refiner_model() -> str:
    load_dotenv()
    model = os.getenv("PROMPT_REFINER_MODEL")
    if not model:
        raise MissingConfigurationError(
            "PROMPT_REFINER_MODEL must be set in environment."
        )
    return model


__all__ = ["ResearchConfig", "_default_deep_research_model"]
