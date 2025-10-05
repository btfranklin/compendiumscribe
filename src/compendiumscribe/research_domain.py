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
    stream_progress: bool = True
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

    if config.stream_progress:
        return _execute_deep_research_streaming(
            client,
            request_payload,
            config,
        )

    response = client.responses.create(**request_payload)

    status = (
        _coerce_optional_string(_get_field(response, "status"))
        or "completed"
    )
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

    final_status = (
        _coerce_optional_string(_get_field(response, "status"))
        or "completed"
    )
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
    last_status = (
        _coerce_optional_string(_get_field(current, "status"))
        or "queued"
    )
    idle_polls = 0

    _emit_progress(
        config,
        phase="deep_research",
        status="in_progress",
        message=f"Deep research job started with status '{last_status}'.",
        metadata={"status": last_status},
    )

    while True:
        status_value = (
            _coerce_optional_string(_get_field(current, "status"))
            or "completed"
        )
        if status_value not in {"in_progress", "queued"}:
            break

        attempts += 1
        if attempts > config.max_poll_attempts:
            raise DeepResearchError(
                "Timed out waiting for deep research to finish."
            )
        time.sleep(config.poll_interval_seconds)
        current = client.responses.retrieve(_get_field(current, "id"))

        status = (
            _coerce_optional_string(_get_field(current, "status"))
            or "completed"
        )

        if status != last_status:
            last_status = status
            idle_polls = 0
            _emit_progress(
                config,
                phase="deep_research",
                status="update",
                message=f"Deep research status changed to '{status}'.",
                metadata={"status": status, "poll_attempt": attempts},
            )
        else:
            idle_polls += 1
            if idle_polls in {1, 3} or idle_polls % 5 == 0:
                _emit_progress(
                    config,
                    phase="deep_research",
                    status="in_progress",
                    message=(
                        "Deep research still running; awaiting updated "
                        f"status (poll #{attempts})."
                    ),
                    metadata={
                        "status": status,
                        "poll_attempt": attempts,
                    },
                )

        summaries = _summaries_from_trace_events(
            _iter_trace_progress_events(current), seen_tokens
        )
        for summary in summaries:
            _emit_progress(
                config,
                phase="trace",
                status=summary["status"],
                message=summary["message"],
                metadata=summary["metadata"],
            )

    return current


# ---------------------------------------------------------------------------
# Streaming execution
# ---------------------------------------------------------------------------


def _execute_deep_research_streaming(
    client: OpenAI,
    request_payload: dict[str, Any],
    config: ResearchConfig,
):
    payload = dict(request_payload)

    if payload.get("background"):
        payload["background"] = False
        _emit_progress(
            config,
            phase="deep_research",
            status="update",
            message=(
                "Streaming requires synchronous execution; "
                "disabling background mode."
            ),
        )

    payload["stream"] = True

    try:
        stream = client.responses.create(**payload)
    except TypeError as exc:
        raise RuntimeError(
            "OpenAI client does not support streaming responses; "
            "upgrade the SDK to a version that implements the Responses "
            "streaming protocol."
        ) from exc

    seen_trace_tokens: set[str] = set()
    stream_state: dict[str, Any] = {"status_events": set()}
    final_response: Any | None = None

    _emit_progress(
        config,
        phase="deep_research",
        status="in_progress",
        message="Streaming deep research events from OpenAI.",
    )

    for event in stream:
        response_candidate = _handle_stream_event(
            event,
            config=config,
            seen_trace_tokens=seen_trace_tokens,
            stream_state=stream_state,
        )
        if response_candidate is not None:
            final_response = response_candidate

    if final_response is None and hasattr(stream, "get_final_response"):
        final_response = stream.get_final_response()

    if final_response is None:
        raise DeepResearchError(
            "Deep research stream completed without a final response."
        )

    final_status = (
        _coerce_optional_string(_get_field(final_response, "status"))
        or "completed"
    )
    if final_status != "completed":
        raise DeepResearchError(
            f"Deep research did not complete successfully: {final_status}"
        )

    _emit_progress(
        config,
        phase="deep_research",
        status="completed",
        message="Deep research stream finished; decoding payload.",
        metadata={"status": final_status},
    )

    return final_response


def _handle_stream_event(
    event: Any,
    *,
    config: ResearchConfig,
    seen_trace_tokens: set[str],
    stream_state: dict[str, Any],
) -> Any | None:
    event_type = _coerce_optional_string(_get_field(event, "type"))
    if not event_type:
        return None

    normalized = event_type.lower()

    if normalized in {"response.created", "response.in_progress"}:
        status_events = stream_state.setdefault("status_events", set())
        if normalized not in status_events:
            status_events.add(normalized)
            status = (
                "starting"
                if normalized == "response.created"
                else "in_progress"
            )
            _emit_progress(
                config,
                phase="deep_research",
                status=status,
                message=f"Deep research status event: {event_type}.",
            )
        return None

    if normalized in {"response.failed", "response.error", "error"}:
        message = _extract_stream_error_message(event) or event_type
        raise DeepResearchError(
            f"Deep research stream reported an error: {message}"
        )

    if normalized == "response.output_item.added":
        item = _get_field(event, "item")
        if item is not None:
            _emit_trace_updates_from_item(
                item,
                config=config,
                seen_tokens=seen_trace_tokens,
            )
        return None

    if normalized == "response.output_item.delta":
        delta = _get_field(event, "delta")
        if delta is not None:
            _emit_trace_updates_from_item(
                delta,
                config=config,
                seen_tokens=seen_trace_tokens,
            )
        return None

    if normalized in {
        "response.output_text.delta",
        "response.output_text.done",
        "response.output_text.added",
        "response.content_part.added",
        "response.content_part.delta",
    }:
        # These events contribute to the final payload but do not affect
        # progress reporting directly.
        return None

    if normalized == "response.completed":
        response_obj = _get_field(event, "response")
        if response_obj is not None:
            return response_obj
        return None

    return None


def _emit_trace_updates_from_item(
    item: Any,
    *,
    config: ResearchConfig,
    seen_tokens: set[str],
) -> None:
    event_snapshot = _trace_event_from_item(item)
    if not event_snapshot:
        return

    summaries = _summaries_from_trace_events([event_snapshot], seen_tokens)
    for summary in summaries:
        _emit_progress(
            config,
            phase="trace",
            status=summary.get("status", "update"),
            message=summary["message"],
            metadata=summary.get("metadata"),
        )


def _extract_stream_error_message(event: Any) -> str:
    error = _get_field(event, "error")
    if error is None:
        message = _get_field(event, "message")
        return _coerce_optional_string(message) or "unknown error"

    if isinstance(error, dict):
        message = _coerce_optional_string(error.get("message"))
        if message:
            return message
        code = _coerce_optional_string(error.get("code"))
        if code:
            return code
        return json.dumps(error, default=str)

    return _coerce_optional_string(error) or "unknown error"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_deep_research_response(response: Any) -> dict[str, Any]:
    text_payload = _collect_response_text(response)
    return _decode_json_payload(text_payload)


def _collect_response_text(response: Any) -> str:
    output_text = _get_field(response, "output_text")
    if output_text:
        return str(output_text).strip()

    output_items = _get_field(response, "output")
    text_parts: list[str] = []

    if output_items:
        for item in output_items:
            item_type = _coerce_optional_string(_get_field(item, "type"))
            if item_type == "message":
                for content in _get_field(item, "content") or []:
                    text_value = _coerce_optional_string(
                        _get_field(content, "text")
                    )
                    if not text_value:
                        text_value = _coerce_optional_string(
                            _get_field(content, "value")
                        )
                    if text_value:
                        text_parts.append(text_value)
            elif item_type == "output_text":
                text = _coerce_optional_string(_get_field(item, "text"))
                if text:
                    text_parts.append(text)

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
    output_items = _get_field(response, "output")
    trace: list[dict[str, Any]] = []

    if not output_items:
        return trace

    for item in output_items:
        event_snapshot = _trace_event_from_item(item)
        if event_snapshot:
            trace.append(event_snapshot)

    return trace


def _trace_event_from_item(item: Any) -> dict[str, Any] | None:
    item_type = _coerce_optional_string(_get_field(item, "type")) or ""
    if not item_type.endswith("_call"):
        return None

    event_id = _coerce_optional_string(_get_field(item, "id"))
    status = _coerce_optional_string(_get_field(item, "status"))
    action_snapshot = _simplify_action_snapshot(_get_field(item, "action"))
    response_snapshot = _normalize_response_snapshot(
        _get_field(item, "response") or _get_field(item, "result")
    )

    return {
        "id": event_id,
        "type": item_type,
        "status": status,
        "action": action_snapshot,
        "response": response_snapshot,
    }


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


def _summaries_from_trace_events(
    events: Iterable[dict[str, Any]],
    seen_tokens: set[str],
) -> list[dict[str, Any]]:
    search_queries: list[str] = []
    open_pages = 0
    find_in_page = 0
    code_runs = 0
    fallbacks: list[dict[str, Any]] = []

    for event in events:
        token = _trace_event_token(event)
        if token in seen_tokens:
            continue
        seen_tokens.add(token)

        action = event.get("action") or {}
        action_type = str(action.get("type", "")).lower()
        query = _coerce_optional_string(action.get("query"))
        event_type = str(event.get("type", "")).lower()

        if event_type.endswith("web_search_call") or action_type == "search":
            if query:
                search_queries.append(query)
            else:
                fallbacks.append(event)
            continue

        if "open_page" in event_type:
            open_pages += 1
            continue

        if "find_in_page" in event_type or action_type == "find":
            find_in_page += 1
            continue

        if "code_interpreter" in event_type:
            code_runs += 1
            continue

        fallbacks.append(event)

    summaries: list[dict[str, Any]] = []

    if search_queries:
        message = f"Exploring sources: {_format_query_list(search_queries)}"
        summaries.append(
            {
                "message": message,
                "status": "update",
                "metadata": {
                    "type": "search_summary",
                    "queries": search_queries,
                },
            }
        )

    if open_pages or find_in_page:
        parts: list[str] = []
        if open_pages:
            parts.append(f"reviewing {open_pages} pages")
        if find_in_page:
            parts.append(f"scanning {find_in_page} passages")
        message = f"Following trails: {' and '.join(parts)}"
        summaries.append(
            {
                "message": message,
                "status": "update",
                "metadata": {
                    "type": "navigation_summary",
                    "open_pages": open_pages,
                    "find_operations": find_in_page,
                },
            }
        )

    if code_runs:
        message = f"Running code interpreter ({code_runs} sessions)."
        summaries.append(
            {
                "message": message,
                "status": "update",
                "metadata": {
                    "type": "code_interpreter_summary",
                    "runs": code_runs,
                },
            }
        )

    for event in fallbacks:
        message = _summarize_trace_event(event)
        if not message:
            continue
        summaries.append(
            {
                "message": message,
                "status": event.get("status") or "update",
                "metadata": {
                    "type": "trace_event",
                    "event": event,
                },
            }
        )

    return summaries


def _format_query_list(queries: list[str], limit: int = 3) -> str:
    unique_queries: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = query.strip()
        if not normalized:
            continue
        fingerprint = normalized.lower()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique_queries.append(normalized)

    if not unique_queries:
        return "current search focus"

    display = [f'"{item}"' for item in unique_queries[:limit]]
    if len(unique_queries) > limit:
        display.append(f"(+{len(unique_queries) - limit} more)")
    return ", ".join(display)


def _trace_event_token(event: dict[str, Any]) -> str:
    event_id = event.get("id")
    if event_id:
        return f"id:{event_id}"

    action = event.get("action") or {}
    query = _coerce_optional_string(action.get("query"))
    if query:
        return f"search:{query.lower()}"

    action_name = _coerce_optional_string(action.get("name"))
    if action_name:
        return f"action:{action_name.lower()}"

    event_type = _coerce_optional_string(event.get("type")) or "generic"
    action_repr = json.dumps(action, sort_keys=True, default=str)
    return f"{event_type}:{action_repr}"


def _iter_trace_progress_events(response: Any) -> Iterable[dict[str, Any]]:
    output_items = getattr(response, "output", None)
    if not output_items:
        return []

    events: list[dict[str, Any]] = []
    for item in output_items:
        item_type = _coerce_optional_string(_get_field(item, "type"))
        if not item_type or not item_type.endswith("_call"):
            continue

        event_id = _coerce_optional_string(_get_field(item, "id"))
        status = _coerce_optional_string(_get_field(item, "status"))
        action_snapshot = _simplify_action_snapshot(
            _get_field(item, "action")
        )

        events.append(
            {
                "id": event_id,
                "type": item_type,
                "status": status or "update",
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
                snapshot[key] = _stringify_metadata_value(value)
        return snapshot

    snapshot = {}
    for key in ACTION_SUMMARY_KEYS:
        value = getattr(action, key, None)
        if value not in (None, ""):
            snapshot[key] = _stringify_metadata_value(value)
    return snapshot


def _normalize_response_snapshot(response: Any) -> Any:
    if response is None:
        return None
    if isinstance(response, (str, int, float, bool)):
        return response
    if isinstance(response, dict):
        return {
            key: _stringify_metadata_value(value)
            for key, value in response.items()
        }
    if isinstance(response, list):
        return [_stringify_metadata_value(item) for item in response]
    return _stringify_metadata_value(response)


def _stringify_metadata_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            key: _stringify_metadata_value(val)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_stringify_metadata_value(item) for item in value]
    return str(value)
