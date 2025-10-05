from __future__ import annotations

import importlib.resources as resources
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from string import Template
from typing import Any, Callable, Iterable, Literal

from dotenv import load_dotenv

from openai import OpenAI
from .model import Compendium


class DeepResearchError(RuntimeError):
    """Raised when the deep research workflow cannot complete successfully."""


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


ProgressPhase = Literal[
    "planning",
    "prompt_composition",
    "deep_research",
    "trace",
    "completion",
]

ProgressStatus = Literal[
    "starting",
    "in_progress",
    "update",
    "completed",
    "error",
]

ACTION_SUMMARY_KEYS = (
    "type",
    "name",
    "query",
    "input",
    "instructions",
    "code",
    "prompt",
)


@dataclass(slots=True)
class ResearchProgress:
    """Represents a progress update emitted during the research workflow."""

    phase: ProgressPhase
    status: ProgressStatus
    message: str
    metadata: dict[str, Any] | None = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


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
        from .create_llm_clients import create_openai_client

        client = create_openai_client(timeout=config.request_timeout_seconds)

    normalized_topic = topic.strip()

    try:
        _emit_progress(
            config,
            phase="planning",
            status="starting",
            message=f"Normalizing topic '{normalized_topic}'.",
            metadata={"topic": normalized_topic},
        )

        plan = None
        if config.use_prompt_refinement:
            _emit_progress(
                config,
                phase="planning",
                status="in_progress",
                message=(
                    "Requesting research blueprint with "
                    f"{config.prompt_refiner_model}."
                ),
            )
            plan = _generate_research_plan(client, normalized_topic, config)

        if plan is None:
            _emit_progress(
                config,
                phase="planning",
                status="update",
                message="Falling back to default research blueprint.",
            )
            plan = _default_research_plan(normalized_topic)
        else:
            _emit_progress(
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

        prompt = _compose_deep_research_prompt(normalized_topic, plan)

        _emit_progress(
            config,
            phase="prompt_composition",
            status="completed",
            message="Deep research assignment prepared.",
            metadata={"sections": len(plan.get("key_sections", []) or [])},
        )

        response = _execute_deep_research(client, prompt, config)

        _emit_progress(
            config,
            phase="deep_research",
            status="completed",
            message="Deep research run finished; decoding payload.",
        )

        payload = _parse_deep_research_response(response)
        payload.setdefault("trace", _extract_trace_events(response))

        _emit_progress(
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
        _emit_progress(
            config,
            phase="completion",
            status="error",
            message=str(exc),
        )
        raise


# ---------------------------------------------------------------------------
# Planning phase
# ---------------------------------------------------------------------------


def _emit_progress(
    config: ResearchConfig,
    *,
    phase: ProgressPhase,
    status: ProgressStatus,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    callback = config.progress_callback
    if callback is None:
        return

    try:
        callback(
            ResearchProgress(
                phase=phase,
                status=status,
                message=message,
                metadata=metadata,
            )
        )
    except Exception:
        # Progress callbacks must never break the research workflow.
        return


def _default_deep_research_model() -> str:
    load_dotenv()
    env_value = os.getenv("RESEARCH_MODEL")
    if env_value:
        stripped = env_value.strip()
        if stripped:
            return stripped
    return "o3-deep-research"


def _generate_research_plan(
    client: OpenAI,
    topic: str,
    config: ResearchConfig,
) -> dict[str, Any] | None:
    template = _load_prompt_template("topic_blueprint.md")
    rendered = template.substitute(topic=topic)

    response = client.responses.create(
        model=config.prompt_refiner_model,
        input=rendered,
    )

    try:
        return _decode_json_payload(_collect_response_text(response))
    except DeepResearchError:
        return None


def _default_research_plan(topic: str) -> dict[str, Any]:
    return {
        "primary_objective": (
            f"Compile a multi-layered compendium covering {topic}"
        ),
        "audience": (
            "Practitioners and researchers seeking a strategic overview"
        ),
        "key_sections": [
            {
                "title": "Foundations",
                "focus": "Core concepts, definitions, and history",
            },
            {
                "title": "Current Landscape",
                "focus": "Recent developments, stakeholders, and adoption",
            },
            {
                "title": "Opportunities and Risks",
                "focus": "Emerging trends, challenges, and future outlook",
            },
        ],
        "research_questions": [
            "What are the most influential recent discoveries or events?",
            "Which organizations or individuals are shaping the field?",
            "What controversies or open debates remain unresolved?",
        ],
        "methodology_preferences": [
            "Prioritize primary sources published within the last five years",
            "Cross-validate critical facts across multiple reputable outlets",
            (
                "Highlight quantitative evidence and concrete metrics when "
                "available"
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def _compose_deep_research_prompt(topic: str, plan: dict[str, Any]) -> str:
    template = _load_prompt_template("deep_research_assignment.md")

    sections = plan.get("key_sections", [])
    if not isinstance(sections, Iterable):
        sections = []
    section_lines: list[str] = []
    for item in sections:
        title = item.get("title", "Section")
        focus = (item.get("focus", "") or "").strip()
        section_lines.append(f"- {title}: {focus}")

    research_questions = plan.get("research_questions", [])
    if not isinstance(research_questions, Iterable):
        research_questions = []
    question_lines = [f"- {question}" for question in research_questions]

    methodology = plan.get("methodology_preferences", [])
    if not isinstance(methodology, Iterable):
        methodology = []
    methodology_lines = [f"- {step}" for step in methodology]

    schema = json.dumps(
        {
            "topic_overview": "string",
            "methodology": ["string", "..."],
            "sections": [
                {
                    "id": "string",
                    "title": "string",
                    "summary": "string",
                    "key_terms": ["string", "..."],
                    "guiding_questions": ["string", "..."],
                    "insights": [
                        {
                            "title": "string",
                            "evidence": "string",
                            "implications": "string | null",
                            "citations": ["string", "..."],
                        }
                    ],
                }
            ],
            "citations": [
                {
                    "id": "string",
                    "title": "string",
                    "url": "string",
                    "publisher": "string | null",
                    "published_at": "string | null",
                    "summary": "string | null",
                }
            ],
            "open_questions": ["string", "..."],
        },
        indent=2,
    )

    section_bullets = (
        "\n".join(section_lines) or "- No specific sections provided"
    )
    question_bullets = (
        "\n".join(question_lines) or "- Derive the most pertinent questions"
    )
    methodology_bullets = (
        "\n".join(methodology_lines)
        or "- Combine qualitative synthesis with quantitative evidence"
    )

    return template.substitute(
        topic=topic,
        primary_objective=plan.get(
            "primary_objective",
            "Produce a research compendium",
        ),
        audience=plan.get("audience", "Analytical readers"),
        section_bullets=section_bullets,
        question_bullets=question_bullets,
        methodology_bullets=methodology_bullets,
        schema=schema,
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _execute_deep_research(
    client: OpenAI,
    prompt: str,
    config: ResearchConfig,
):
    tools: list[dict[str, Any]] = []
    if config.use_web_search:
        tools.append({"type": "web_search_preview"})
    if config.enable_code_interpreter:
        tools.append(
            {"type": "code_interpreter", "container": {"type": "auto"}}
        )

    if not tools:
        raise DeepResearchError(
            "Deep research requires enabling web search or code interpreter."
        )

    request_payload: dict[str, Any] = {
        "model": config.deep_research_model,
        "input": prompt,
        "background": config.background,
        "tools": tools,
    }

    if config.max_tool_calls is not None:
        request_payload["max_tool_calls"] = config.max_tool_calls

    _emit_progress(
        config,
        phase="deep_research",
        status="starting",
        message="Submitting deep research request to OpenAI.",
    )

    response = client.responses.create(**request_payload)

    status = getattr(response, "status", "completed")
    if status in {"in_progress", "queued"}:
        response = _await_completion(client, response, config)
    else:
        _emit_progress(
            config,
            phase="deep_research",
            status="completed",
            message="Deep research completed synchronously.",
            metadata={"status": status},
        )

    final_status = getattr(response, "status", "completed")
    if final_status != "completed":
        raise DeepResearchError(
            f"Deep research did not complete successfully: {final_status}"
        )

    return response


def _await_completion(
    client: OpenAI,
    response: Any,
    config: ResearchConfig,
):
    attempts = 0
    current = response
    seen_tokens: set[str] = set()
    last_status = getattr(current, "status", "queued")

    _emit_progress(
        config,
        phase="deep_research",
        status="in_progress",
        message=f"Deep research job started with status '{last_status}'.",
        metadata={"status": last_status},
    )

    while getattr(current, "status", "completed") in {"in_progress", "queued"}:
        attempts += 1
        if attempts > config.max_poll_attempts:
            raise DeepResearchError(
                "Timed out waiting for deep research to finish."
            )
        time.sleep(config.poll_interval_seconds)
        current = client.responses.retrieve(current.id)

        status = getattr(current, "status", "completed")

        if status != last_status:
            last_status = status
            _emit_progress(
                config,
                phase="deep_research",
                status="update",
                message=f"Deep research status changed to '{status}'.",
                metadata={"status": status, "poll_attempt": attempts},
            )
        else:
            _emit_progress(
                config,
                phase="deep_research",
                status="in_progress",
                message=(
                    "Awaiting deep research completion; "
                    "no status change detected."
                ),
                metadata={"status": status, "poll_attempt": attempts},
            )

        for event in _iter_trace_progress_events(current):
            message = _summarize_trace_event(event)
            if message:
                token = str(event.get("id") or message)
                if token in seen_tokens:
                    continue
                seen_tokens.add(token)
                _emit_progress(
                    config,
                    phase="trace",
                    status=event.get("status") or "update",
                    message=message,
                    metadata=event,
                )

    return current


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_deep_research_response(response: Any) -> dict[str, Any]:
    text_payload = _collect_response_text(response)
    return _decode_json_payload(text_payload)


def _collect_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text).strip()

    output_items = getattr(response, "output", None)
    text_parts: list[str] = []

    if output_items:
        for item in output_items:
            data = _object_to_dict(item)
            item_type = data.get("type")
            if item_type == "message":
                for content in data.get("content", []):
                    content_data = _object_to_dict(content)
                    text = (
                        content_data.get("text")
                        or content_data.get("value")
                    )
                    if text:
                        text_parts.append(str(text))
            elif item_type == "output_text":
                text = data.get("text")
                if text:
                    text_parts.append(str(text))

    if text_parts:
        return "".join(text_parts).strip()

    raise DeepResearchError(
        "Deep research response did not include textual output."
    )


def _decode_json_payload(text: str) -> dict[str, Any]:
    candidate = text.strip()

    if candidate.startswith("```"):
        candidate = candidate.strip("`").strip()
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()

    if candidate and not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1:
            raise DeepResearchError(
                "Unable to locate JSON object in response."
            )
        candidate = candidate[start:end + 1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DeepResearchError(
            "Deep research response was not valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise DeepResearchError(
            "Expected JSON object at top level of response."
        )

    return payload


def _extract_trace_events(response: Any) -> list[dict[str, Any]]:
    output_items = getattr(response, "output", None)
    trace: list[dict[str, Any]] = []

    if not output_items:
        return trace

    for item in output_items:
        data = _object_to_dict(item)
        item_type = data.get("type", "")
        if item_type.endswith("_call"):
            trace.append(
                {
                    "id": data.get("id"),
                    "type": item_type,
                    "status": data.get("status"),
                    "action": data.get("action") or {},
                    "response": data.get("response") or data.get("result"),
                }
            )

    return trace


def _summarize_trace_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "")).strip() or "tool_call"
    status = str(event.get("status", "")).strip()
    action = event.get("action") or {}

    action_type = str(action.get("type", "")).strip()
    action_name = action_type or str(action.get("name", "")).strip()

    label = action_name or event_type
    summary = label
    if status:
        summary = f"{summary} [{status}]"

    detail = None
    for key in ("query", "input", "instructions", "code", "prompt"):
        value = action.get(key)
        if isinstance(value, str) and value.strip():
            detail = _truncate_text(value)
            break

    if detail:
        summary = f"{summary}: {detail}"

    return summary


def _iter_trace_progress_events(response: Any) -> Iterable[dict[str, Any]]:
    output_items = getattr(response, "output", None)
    if not output_items:
        return []

    events: list[dict[str, Any]] = []
    for item in output_items:
        item_type = _coerce_optional_string(_get_field(item, "type"))
        if not item_type or not item_type.endswith("_call"):
            continue

        event_id = _get_field(item, "id")
        status = _coerce_optional_string(_get_field(item, "status"))
        action_snapshot = _simplify_action_snapshot(
            _get_field(item, "action")
        )

        events.append(
            {
                "id": event_id,
                "type": item_type,
                "status": status,
                "action": action_snapshot,
            }
        )

    return events


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _load_prompt_template(filename: str) -> Template:
    prompt_package = resources.files("compendiumscribe.prompts")
    prompt_text = prompt_package.joinpath(filename).read_text("utf-8")
    normalized = _strip_leading_markdown_header(prompt_text)
    return Template(normalized)


def _strip_leading_markdown_header(text: str) -> str:
    lines = text.splitlines()
    trimmed: list[str] = []
    skipping = True

    for line in lines:
        stripped = line.strip()
        if skipping and stripped.startswith("# "):
            continue
        if skipping and not stripped:
            continue

        skipping = False
        trimmed.append(line)

    return "\n".join(trimmed).lstrip()


def _object_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    for method_name in ("model_dump", "to_dict", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            result = method()
            if isinstance(result, dict):
                return result

    if hasattr(value, "__dict__"):
        return {
            k: getattr(value, k) for k in vars(value) if not k.startswith("_")
        }

    return {}


def _truncate_text(value: str, max_length: int = 120) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def _get_field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _coerce_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _simplify_action_snapshot(action: Any) -> dict[str, Any]:
    if not action:
        return {}

    if isinstance(action, dict):
        snapshot: dict[str, Any] = {}
        for key in ACTION_SUMMARY_KEYS:
            value = action.get(key)
            if value not in (None, ""):
                snapshot[key] = value
        return snapshot

    snapshot = {}
    for key in ACTION_SUMMARY_KEYS:
        value = getattr(action, key, None)
        if value not in (None, ""):
            snapshot[key] = value
    return snapshot
