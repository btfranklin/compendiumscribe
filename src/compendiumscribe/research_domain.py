from __future__ import annotations

import importlib.resources as resources
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from string import Template
from typing import Any, Iterable, Sequence

from openai import OpenAI

from .model import Compendium


class DeepResearchError(RuntimeError):
    """Raised when the deep research workflow cannot complete successfully."""


@dataclass
class ResearchConfig:
    """Configuration flags for the deep research pipeline."""

    deep_research_model: str = "o3-deep-research"
    prompt_refiner_model: str = "gpt-4.1-mini"
    use_prompt_refinement: bool = True
    background: bool = True
    poll_interval_seconds: float = 5.0
    max_poll_attempts: int = 240
    enable_code_interpreter: bool = True
    use_web_search: bool = True
    vector_store_ids: Sequence[str] = field(default_factory=tuple)
    max_tool_calls: int | None = None
    request_timeout_seconds: int = 3600


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

    plan = None
    if config.use_prompt_refinement:
        plan = _generate_research_plan(client, normalized_topic, config)

    if plan is None:
        plan = _default_research_plan(normalized_topic)

    prompt = _compose_deep_research_prompt(normalized_topic, plan)

    response = _execute_deep_research(client, prompt, config)

    payload = _parse_deep_research_response(response)
    payload.setdefault("trace", _extract_trace_events(response))

    return Compendium.from_payload(
        topic=normalized_topic,
        payload=payload,
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Planning phase
# ---------------------------------------------------------------------------


def _generate_research_plan(client: OpenAI, topic: str, config: ResearchConfig) -> dict[str, Any] | None:
    template = _load_prompt_template("10_topic_blueprint.prompt.md")
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
        "primary_objective": f"Compile a multi-layered compendium covering {topic}",
        "audience": "Practitioners and researchers seeking a strategic overview",
        "key_sections": [
            {"title": "Foundations", "focus": "Core concepts, definitions, and history"},
            {"title": "Current Landscape", "focus": "Recent developments, stakeholders, and adoption"},
            {"title": "Opportunities and Risks", "focus": "Emerging trends, challenges, and future outlook"},
        ],
        "research_questions": [
            "What are the most influential recent discoveries or events?",
            "Which organisations or individuals are shaping the field?",
            "What controversies or open debates remain unresolved?",
        ],
        "methodology_preferences": [
            "Prioritise primary sources published within the last five years",
            "Cross-validate critical facts across multiple reputable outlets",
            "Highlight quantitative evidence and concrete metrics when available",
        ],
    }


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def _compose_deep_research_prompt(topic: str, plan: dict[str, Any]) -> str:
    template = _load_prompt_template("20_deep_research.prompt.md")

    sections = plan.get("key_sections", [])
    if not isinstance(sections, Iterable):
        sections = []
    section_lines = [
        f"- {item.get('title', 'Section')}: {item.get('focus', '').strip()}" for item in sections
    ]

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

    return template.substitute(
        topic=topic,
        primary_objective=plan.get("primary_objective", "Produce a research compendium"),
        audience=plan.get("audience", "Analytical readers"),
        section_bullets="\n".join(section_lines) or "- No specific sections provided",
        question_bullets="\n".join(question_lines) or "- Derive the most pertinent questions",
        methodology_bullets="\n".join(methodology_lines)
        or "- Combine qualitative synthesis with quantitative evidence",
        schema=schema,
    )


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _execute_deep_research(client: OpenAI, prompt: str, config: ResearchConfig):
    tools: list[dict[str, Any]] = []
    if config.use_web_search:
        tools.append({"type": "web_search_preview"})
    if config.vector_store_ids:
        tools.append({"type": "file_search", "vector_store_ids": list(config.vector_store_ids)})
    if config.enable_code_interpreter:
        tools.append({"type": "code_interpreter", "container": {"type": "auto"}})

    if not tools:
        raise DeepResearchError(
            "Deep research requires at least one data source tool (web search or file search)."
        )

    request_payload: dict[str, Any] = {
        "model": config.deep_research_model,
        "input": prompt,
        "background": config.background,
        "tools": tools,
    }

    if config.max_tool_calls is not None:
        request_payload["max_tool_calls"] = config.max_tool_calls

    response = client.responses.create(**request_payload)

    status = getattr(response, "status", "completed")
    if status in {"in_progress", "queued"}:
        response = _await_completion(client, response, config)

    final_status = getattr(response, "status", "completed")
    if final_status != "completed":
        raise DeepResearchError(f"Deep research did not complete successfully: {final_status}")

    return response


def _await_completion(client: OpenAI, response: Any, config: ResearchConfig):
    attempts = 0
    current = response

    while getattr(current, "status", "completed") in {"in_progress", "queued"}:
        attempts += 1
        if attempts > config.max_poll_attempts:
            raise DeepResearchError("Timed out waiting for deep research to finish.")
        time.sleep(config.poll_interval_seconds)
        current = client.responses.retrieve(current.id)

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
                    text = content_data.get("text") or content_data.get("value")
                    if text:
                        text_parts.append(str(text))
            elif item_type == "output_text":
                text = data.get("text")
                if text:
                    text_parts.append(str(text))

    if text_parts:
        return "".join(text_parts).strip()

    raise DeepResearchError("Deep research response did not include textual output.")


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
            raise DeepResearchError("Unable to locate JSON object in response.")
        candidate = candidate[start : end + 1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise DeepResearchError("Deep research response was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise DeepResearchError("Expected JSON object at top level of response.")

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


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _load_prompt_template(filename: str) -> Template:
    prompt_text = resources.files("compendiumscribe.prompts").joinpath(filename).read_text("utf-8")
    return Template(prompt_text)


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
        return {k: getattr(value, k) for k in vars(value) if not k.startswith("_")}

    return {}
