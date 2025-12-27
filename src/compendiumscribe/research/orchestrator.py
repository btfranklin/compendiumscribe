from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, TYPE_CHECKING

from openai import OpenAI

from ..compendium import Compendium
from .config import ResearchConfig
from .errors import DeepResearchError, ResearchTimeoutError
from .execution import execute_deep_research
from .parsing import parse_deep_research_response
from .planning import (
    compose_deep_research_prompt,
    default_research_plan,
    generate_research_plan,
)
from .progress import emit_progress
from .utils import coerce_optional_string, get_field

if TYPE_CHECKING:
    from .cancellation import CancellationContext


def build_compendium(
    topic: str,
    *,
    client: OpenAI | None = None,
    config: ResearchConfig | None = None,
    cancel_ctx: "CancellationContext | None" = None,
) -> Compendium:
    """High-level API: build a compendium for a topic using deep research."""

    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    config = config or ResearchConfig()

    if client is None:
        from ..create_llm_clients import create_openai_client

        client = create_openai_client(timeout=config.request_timeout_seconds)

    normalized_topic = topic.strip()
    compendium_title = normalized_topic

    try:
        emit_progress(
            config,
            phase="planning",
            status="starting",
            message=f"Normalizing topic '{normalized_topic}'.",
            metadata={"topic": normalized_topic},
        )

        plan: dict[str, Any] | None = None
        if config.use_prompt_refinement:
            emit_progress(
                config,
                phase="planning",
                status="in_progress",
                message=(
                    "Requesting research blueprint with "
                    f"{config.prompt_refiner_model}."
                ),
            )
            plan = generate_research_plan(client, normalized_topic, config)

        if plan is None:
            emit_progress(
                config,
                phase="planning",
                status="update",
                message="Falling back to default research blueprint.",
            )
            plan = default_research_plan(normalized_topic)
        else:
            key_sections = plan.get("key_sections", []) or []
            plan_json = json.dumps(plan, indent=2)
            emit_progress(
                config,
                phase="planning",
                status="completed",
                message="Received refined research blueprint.",
                metadata={
                    "sections": len(key_sections),
                    "questions": len(
                        plan.get("research_questions", []) or []
                    ),
                    "section_titles": [
                        s.get("title") for s in key_sections if s.get("title")
                    ],
                    "plan_json": plan_json,
                },
            )

        compendium_title = (
            coerce_optional_string(plan.get("title"))
            or normalized_topic
        )
        prompt = compose_deep_research_prompt(normalized_topic, plan)

        emit_progress(
            config,
            phase="prompt_composition",
            status="completed",
            message="Deep research assignment prepared.",
            metadata={"sections": len(plan.get("key_sections", []) or [])},
        )

        response = execute_deep_research(client, prompt, config, cancel_ctx)

        payload = parse_deep_research_response(response)

        emit_progress(
            config,
            phase="completion",
            status="in_progress",
            message="Constructing compendium model.",
        )

        return Compendium.from_payload(
            topic=compendium_title,
            payload=payload,
            generated_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        if isinstance(exc, ResearchTimeoutError):
            setattr(exc, "compendium_title", compendium_title)
        emit_progress(
            config,
            phase="completion",
            status="error",
            message=str(exc),
        )
        raise


def recover_compendium(
    research_id: str,
    topic: str,
    *,
    client: OpenAI | None = None,
    config: ResearchConfig | None = None,
) -> Compendium:
    """Finish a previously timed-out research run and return the compendium."""
    config = config or ResearchConfig()

    if client is None:
        from ..create_llm_clients import create_openai_client

        client = create_openai_client(timeout=config.request_timeout_seconds)

    response = client.responses.retrieve(research_id)
    status = coerce_optional_string(get_field(response, "status"))

    if status != "completed":
        raise DeepResearchError(
            f"Research is not yet completed (current status: {status})."
        )

    payload = parse_deep_research_response(response)

    return Compendium.from_payload(
        topic=topic,
        payload=payload,
        generated_at=datetime.now(timezone.utc),
    )


__all__ = ["build_compendium", "recover_compendium"]
