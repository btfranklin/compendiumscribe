from __future__ import annotations

import json
from promptdown import StructuredPrompt
from typing import Any, Iterable

from .config import ResearchConfig
from .errors import DeepResearchError
from .parsing import collect_response_text, decode_json_payload


def generate_research_plan(
    client: Any,
    topic: str,
    config: ResearchConfig,
) -> dict[str, Any] | None:
    prompt_obj = load_prompt_template("topic_blueprint.prompt.md")
    # Apply template values
    prompt_obj = prompt_obj.apply_template_values({"topic": topic})

    # Convert to Responses API input
    responses_input = prompt_obj.to_responses_input()

    response = client.responses.create(
        model=config.prompt_refiner_model,
        input=responses_input,
        reasoning={"effort": "high"},
    )

    try:
        return decode_json_payload(collect_response_text(response))
    except DeepResearchError:
        return None


def default_research_plan(topic: str) -> dict[str, Any]:
    return {
        "title": topic,
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


def compose_deep_research_prompt(topic: str, plan: dict[str, Any]) -> Any:
    prompt_obj = load_prompt_template("deep_research_assignment.prompt.md")

    sections = plan.get("key_sections", [])

    def _format_section_line(item: dict[str, Any]) -> str:
        title = item.get("title", "Section")
        focus = (item.get("focus", "") or "").strip()
        return f"{title}: {focus}"

    section_lines = _format_bullets(sections, _format_section_line)

    research_questions = plan.get("research_questions", [])
    question_lines = _format_bullets(research_questions)

    methodology = plan.get("methodology_preferences", [])
    methodology_lines = _format_bullets(methodology)

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

    prompt_obj = prompt_obj.apply_template_values(
        {
            "topic": topic,
            "primary_objective": plan.get(
                "primary_objective",
                "Produce a research compendium",
            ),
            "audience": plan.get("audience", "Analytical readers"),
            "section_bullets": "\n".join(section_lines)
            or "- No specific sections provided",
            "question_bullets": "\n".join(question_lines)
            or "- Derive the most pertinent questions",
            "methodology_bullets": "\n".join(methodology_lines)
            or "- Combine qualitative synthesis with quantitative evidence",
            "schema": schema,
        }
    )

    return prompt_obj.to_responses_input()


def _format_bullets(
    items: Any, formatter: Any | None = None
) -> list[str]:
    """Helper to format a list of items as Markdown bullet points."""
    if not isinstance(items, Iterable):
        return []

    lines: list[str] = []
    for item in items:
        if formatter:
            formatted = formatter(item)
        else:
            formatted = str(item).strip()

        if formatted:
            lines.append(f"- {formatted}")
    return lines


def load_prompt_template(filename: str) -> StructuredPrompt:
    return StructuredPrompt.from_package_resource(
        "compendiumscribe.prompts", filename
    )


__all__ = [
    "compose_deep_research_prompt",
    "default_research_plan",
    "generate_research_plan",
    "load_prompt_template",
]
