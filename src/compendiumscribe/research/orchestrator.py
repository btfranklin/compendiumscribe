from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openai import OpenAI

from ..compendium import Compendium
from .config import ResearchConfig
from .execution import execute_deep_research
from .parsing import (
    extract_trace_events,
    parse_deep_research_response,
)
from .planning import (
    compose_deep_research_prompt,
    default_research_plan,
    generate_research_plan,
)
from .progress import emit_progress


def build_compendium(
    topic: str,
    *,
    client: OpenAI | None = None,
    config: ResearchConfig | None = None,
) -> Compendium:
    """High-level API: build a compendium for a topic using deep research."""

    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    config = config or ResearchConfig()

    if client is None:
        from ..create_llm_clients import create_openai_client

        client = create_openai_client(timeout=config.request_timeout_seconds)

    normalized_topic = topic.strip()

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
            emit_progress(
                config,
                phase="planning",
                status="completed",
                message="Received refined research blueprint.",
                metadata={
                    "sections": len(plan.get("key_sections", []) or []),
                    "questions": len(
                        plan.get("research_questions", []) or []
                    ),
                },
            )

        prompt = compose_deep_research_prompt(normalized_topic, plan)

        emit_progress(
            config,
            phase="prompt_composition",
            status="completed",
            message="Deep research assignment prepared.",
            metadata={"sections": len(plan.get("key_sections", []) or [])},
        )

        response = execute_deep_research(client, prompt, config)

        emit_progress(
            config,
            phase="deep_research",
            status="completed",
            message="Deep research run finished; decoding payload.",
        )

        payload = parse_deep_research_response(response)
        payload.setdefault("trace", extract_trace_events(response))

        emit_progress(
            config,
            phase="completion",
            status="in_progress",
            message="Constructing compendium model.",
        )

        return Compendium.from_payload(
            topic=normalized_topic,
            payload=payload,
            generated_at=datetime.now(timezone.utc),
        )
    except Exception as exc:
        emit_progress(
            config,
            phase="completion",
            status="error",
            message=str(exc),
        )
        raise


__all__ = ["build_compendium"]
