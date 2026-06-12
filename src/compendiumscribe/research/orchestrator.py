from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..compendium import Compendium
from .agents_workflow import (
    build_compendium_with_agents,
    recover_compendium_from_state,
)
from .config import ResearchConfig

if TYPE_CHECKING:
    from .costs import CostTracker
    from .agents_workflow.runner import AgentRunner
    from openai import AsyncOpenAI


def build_compendium(
    topic: str,
    *,
    client: "AsyncOpenAI | None" = None,
    config: ResearchConfig | None = None,
    cost_tracker: "CostTracker | None" = None,
    state_path: Path | None = None,
    output_formats: list[str] | tuple[str, ...] = (),
    runner: "AgentRunner | None" = None,
) -> Compendium:
    """Build a compendium through the bounded Agents SDK workflow."""

    return build_compendium_with_agents(
        topic,
        client=client,
        config=config,
        runner=runner,
        state_path=state_path,
        cost_tracker=cost_tracker,
        output_formats=output_formats,
    )


def recover_compendium(
    state_path: Path,
    *,
    client: "AsyncOpenAI | None" = None,
    config: ResearchConfig | None = None,
    cost_tracker: "CostTracker | None" = None,
    runner: "AgentRunner | None" = None,
) -> Compendium:
    """Resume an Agents SDK research run from a sidecar state file."""

    return recover_compendium_from_state(
        state_path,
        client=client,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
    )


__all__ = ["build_compendium", "recover_compendium"]
