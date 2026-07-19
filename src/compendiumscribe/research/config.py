from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING
import os

from dotenv import load_dotenv

from .errors import MissingConfigurationError

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from .progress import ResearchProgress

load_dotenv()


REQUIRED_PROFILE_ENV_VAR = "CONTRACT4AGENTS_PROFILE"


@dataclass
class ResearchConfig:
    """Configuration flags for the Agents SDK research workflow."""

    contract4agents_profile: str = field(
        default_factory=lambda: os.getenv(REQUIRED_PROFILE_ENV_VAR, "")
    )
    polling_interval_seconds: float = field(
        default_factory=lambda: float(os.getenv("POLLING_INTERVAL_IN_SECONDS", "10.0"))
    )
    max_poll_time_minutes: float = field(
        default_factory=lambda: float(os.getenv("MAX_POLL_TIME_IN_MINUTES", "60.0"))
    )
    max_agent_turns: int = field(
        default_factory=lambda: int(os.getenv("MAX_AGENT_TURNS", "12"))
    )
    request_timeout_seconds: int = 3600
    progress_callback: Callable[["ResearchProgress"], None] | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.contract4agents_profile, str)
            or not self.contract4agents_profile.strip()
        ):
            raise MissingConfigurationError(
                "Missing required Contract4Agents profile selection: "
                f"{REQUIRED_PROFILE_ENV_VAR}"
            )
        self.contract4agents_profile = self.contract4agents_profile.strip()

    def runtime_snapshot(self) -> dict[str, str | int | float]:
        return {
            "contract4agents_profile": self.contract4agents_profile,
            "max_agent_turns": self.max_agent_turns,
            "polling_interval_seconds": self.polling_interval_seconds,
            "max_poll_time_minutes": self.max_poll_time_minutes,
        }


__all__ = ["ResearchConfig", "REQUIRED_PROFILE_ENV_VAR"]
