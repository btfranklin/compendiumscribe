from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING
import os

from dotenv import load_dotenv

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from .progress import ResearchProgress

load_dotenv()


@dataclass
class ResearchConfig:
    """Configuration flags for the Agents SDK research workflow."""

    planner_agent_model: str = field(
        default_factory=lambda: _agent_model_env(
            "PLANNER_AGENT_MODEL", "gpt-5.4"
        )
    )
    research_agent_model: str = field(
        default_factory=lambda: _agent_model_env(
            "RESEARCH_AGENT_MODEL", "gpt-5.4"
        )
    )
    verifier_agent_model: str = field(
        default_factory=lambda: _agent_model_env(
            "VERIFIER_AGENT_MODEL", "gpt-5.4"
        )
    )
    synthesis_agent_model: str = field(
        default_factory=lambda: _agent_model_env(
            "SYNTHESIS_AGENT_MODEL", "gpt-5.4"
        )
    )
    polling_interval_seconds: float = field(
        default_factory=lambda: float(
            os.getenv("POLLING_INTERVAL_IN_SECONDS", "10.0")
        )
    )
    max_poll_time_minutes: float = field(
        default_factory=lambda: float(
            os.getenv("MAX_POLL_TIME_IN_MINUTES", "60.0")
        )
    )
    max_agent_turns: int = field(
        default_factory=lambda: int(os.getenv("MAX_AGENT_TURNS", "12"))
    )
    request_timeout_seconds: int = 3600
    progress_callback: Callable[["ResearchProgress"], None] | None = None

    def model_snapshot(self) -> dict[str, str | int | float]:
        return {
            "planner_agent_model": self.planner_agent_model,
            "research_agent_model": self.research_agent_model,
            "verifier_agent_model": self.verifier_agent_model,
            "synthesis_agent_model": self.synthesis_agent_model,
            "max_agent_turns": self.max_agent_turns,
            "polling_interval_seconds": self.polling_interval_seconds,
            "max_poll_time_minutes": self.max_poll_time_minutes,
        }


def _agent_model_env(name: str, default: str) -> str:
    return os.getenv(name) or default


__all__ = ["ResearchConfig"]
