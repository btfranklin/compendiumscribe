from __future__ import annotations

import importlib.resources as resources
import json
from string import Template
from typing import Any, Iterable

from .config import ResearchConfig
from .errors import DeepResearchError
from .parsing import collect_response_text, decode_json_payload


def generate_research_plan(
    client: Any,
    topic: str,
    config: ResearchConfig,
) -> dict[str, Any] | None:
    template = load_prompt_template("topic_blueprint.md")
    rendered = template.substitute(topic=topic)

    response = client.responses.create(
        model=config.prompt_refiner_model,
        input=rendered,
    )

    try:
        return decode_json_payload(collect_response_text(response))
    except DeepResearchError:
        return None


def default_research_plan(topic: str) -> dict[str, Any]:
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


def compose_deep_research_prompt(topic: str, plan: dict[str, Any]) -> str:
    template = load_prompt_template("deep_research_assignment.md")

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


def load_prompt_template(filename: str) -> Template:
    prompt_package = resources.files("compendiumscribe.prompts")
    prompt_text = prompt_package.joinpath(filename).read_text("utf-8")
    normalized = strip_leading_markdown_header(prompt_text)
    return Template(normalized)


def strip_leading_markdown_header(text: str) -> str:
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


__all__ = [
    "compose_deep_research_prompt",
    "default_research_plan",
    "generate_research_plan",
    "load_prompt_template",
    "strip_leading_markdown_header",
]
