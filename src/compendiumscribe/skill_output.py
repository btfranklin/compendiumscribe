from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re
from typing import Any, Callable

from dotenv import load_dotenv
from promptdown import StructuredPrompt

from .compendium import Compendium
from .research.parsing import collect_response_text, decode_json_payload

load_dotenv()

SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillGenerationError(RuntimeError):
    """Raised when skill naming or authoring fails."""


@dataclass(frozen=True)
class SkillProgress:
    phase: str
    status: str
    message: str
    metadata: dict[str, Any] | None = None


@dataclass
class SkillConfig:
    """Configuration for skill naming and authoring calls."""

    skill_namer_model: str = field(
        default_factory=lambda: os.getenv("SKILL_NAMER_MODEL", "gpt-5.2")
    )
    skill_writer_model: str = field(
        default_factory=lambda: os.getenv("SKILL_WRITER_MODEL", "gpt-5.2")
    )
    reasoning_effort: str = "high"
    max_retries: int = 3
    progress_callback: Callable[[SkillProgress], None] | None = None


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str


def _load_prompt_template(filename: str) -> StructuredPrompt:
    return StructuredPrompt.from_package_resource(
        "compendiumscribe.prompts", filename
    )


def _format_section_summaries(compendium: Compendium) -> str:
    lines = []
    for section in compendium.sections:
        summary = (section.summary or "").strip()
        if summary:
            lines.append(f"- {section.title}: {summary}")
        else:
            lines.append(f"- {section.title}")
    return "\n".join(lines) or "- No sections available"


def _format_section_index(compendium: Compendium) -> str:
    lines = []
    for section in compendium.sections:
        title = section.title.strip() if section.title else ""
        identifier = section.identifier.strip() if section.identifier else ""
        if title and identifier:
            lines.append(f"- {title} ({identifier})")
        elif title:
            lines.append(f"- {title}")
        elif identifier:
            lines.append(f"- {identifier}")
    return "\n".join(lines) or "- No sections available"


def _ensure_ascii(value: str, label: str) -> None:
    if not value:
        return
    if any(ord(char) > 127 for char in value):
        raise SkillGenerationError(
            f"{label} must use ASCII characters only."
        )


def _emit_progress(
    config: SkillConfig,
    phase: str,
    status: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if config.progress_callback is None:
        return
    config.progress_callback(
        SkillProgress(
            phase=phase,
            status=status,
            message=message,
            metadata=metadata,
        )
    )


def _validate_skill_name(name: str) -> None:
    if not name:
        raise SkillGenerationError("Skill name was empty.")
    if len(name) > 64:
        raise SkillGenerationError(
            f"Skill name exceeds 64 characters: {name!r}"
        )
    if not SKILL_NAME_PATTERN.match(name):
        raise SkillGenerationError(
            "Skill name must be lowercase letters, digits, and hyphens only."
        )


def _validate_skill_markdown(
    markdown: str,
    expected_name: str,
    reference_filename: str,
) -> None:
    if not markdown.strip():
        raise SkillGenerationError("SKILL.md content was empty.")
    if not markdown.lstrip().startswith("---"):
        raise SkillGenerationError("SKILL.md missing YAML frontmatter.")
    if "name:" not in markdown or "description:" not in markdown:
        raise SkillGenerationError(
            "SKILL.md frontmatter missing name or description."
        )
    if expected_name not in markdown:
        raise SkillGenerationError(
            "SKILL.md did not include the expected skill name."
        )
    if f"references/{reference_filename}" not in markdown:
        raise SkillGenerationError(
            "SKILL.md did not reference the expected markdown file."
        )
    _ensure_ascii(markdown, "SKILL.md")


def _call_skill_prompt(
    client: Any, model: str, prompt: Any, effort: str
) -> dict[str, Any]:
    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort": effort},
        )
        payload = decode_json_payload(collect_response_text(response))
    except Exception as exc:
        raise SkillGenerationError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise SkillGenerationError("Skill response payload was not JSON.")
    return payload


def generate_skill_metadata(
    client: Any,
    compendium: Compendium,
    config: SkillConfig,
) -> SkillMetadata:
    prompt_obj = _load_prompt_template("skill_name.prompt.md")
    prompt_obj = prompt_obj.apply_template_values(
        {
            "topic": compendium.topic,
            "overview": compendium.overview or "",
            "section_summaries": _format_section_summaries(compendium),
            "section_index": _format_section_index(compendium),
        }
    )
    payload = _call_skill_prompt(
        client,
        config.skill_namer_model,
        prompt_obj.to_responses_input(),
        config.reasoning_effort,
    )

    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip()
    _validate_skill_name(name)
    if not description:
        raise SkillGenerationError("Skill description was empty.")
    _ensure_ascii(description, "Skill description")
    return SkillMetadata(name=name, description=description)


def generate_skill_markdown(
    client: Any,
    compendium: Compendium,
    metadata: SkillMetadata,
    reference_filename: str,
    config: SkillConfig,
) -> str:
    prompt_obj = _load_prompt_template("skill_writer.prompt.md")
    prompt_obj = prompt_obj.apply_template_values(
        {
            "skill_name": metadata.name,
            "skill_description": metadata.description,
            "topic": compendium.topic,
            "overview": compendium.overview or "",
            "section_summaries": _format_section_summaries(compendium),
            "section_index": _format_section_index(compendium),
            "reference_filename": reference_filename,
        }
    )

    payload = _call_skill_prompt(
        client,
        config.skill_writer_model,
        prompt_obj.to_responses_input(),
        config.reasoning_effort,
    )
    markdown = payload.get("skill_markdown")
    if not isinstance(markdown, str):
        raise SkillGenerationError(
            "Skill writer response did not include skill_markdown."
        )
    _validate_skill_markdown(markdown, metadata.name, reference_filename)
    return markdown


def _retry(
    action: Any,
    *,
    max_retries: int,
    config: SkillConfig,
    phase: str,
    action_label: str,
    success_message: str,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        _emit_progress(
            config,
            phase=phase,
            status="in_progress",
            message=action_label,
            metadata={"attempt": attempt, "max_attempts": max_retries},
        )
        try:
            result = action()
        except SkillGenerationError as exc:
            last_error = exc
            _emit_progress(
                config,
                phase=phase,
                status="error",
                message=f"{action_label} failed: {exc}",
                metadata={"attempt": attempt, "max_attempts": max_retries},
            )
            continue
        _emit_progress(
            config,
            phase=phase,
            status="completed",
            message=success_message,
            metadata={"attempt": attempt, "max_attempts": max_retries},
        )
        return result
    if last_error is None:
        raise SkillGenerationError("Skill generation failed unexpectedly.")
    raise last_error


def render_skill_folder(
    compendium: Compendium,
    base_path: Path,
    client: Any,
    config: SkillConfig | None = None,
) -> Path:
    """Render a Compendium into a skill folder with SKILL.md + references."""

    config = config or SkillConfig()
    reference_filename = f"{base_path.name}.md"

    metadata = _retry(
        lambda: generate_skill_metadata(client, compendium, config),
        max_retries=config.max_retries,
        config=config,
        phase="skill_naming",
        action_label=(
            "Generating skill name and description with "
            f"{config.skill_namer_model}"
        ),
        success_message="Skill name and description ready.",
    )
    skill_markdown = _retry(
        lambda: generate_skill_markdown(
            client,
            compendium,
            metadata,
            reference_filename,
            config,
        ),
        max_retries=config.max_retries,
        config=config,
        phase="skill_writing",
        action_label=(
            "Writing SKILL.md with "
            f"{config.skill_writer_model}"
        ),
        success_message="SKILL.md content ready.",
    )

    skill_dir = base_path.parent / metadata.name
    references_dir = skill_dir / "references"
    references_dir.mkdir(parents=True, exist_ok=True)

    reference_path = references_dir / reference_filename
    reference_path.write_text(compendium.to_markdown(), encoding="utf-8")

    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(skill_markdown, encoding="utf-8")

    return skill_dir


__all__ = [
    "SkillConfig",
    "SkillGenerationError",
    "SkillMetadata",
    "SkillProgress",
    "render_skill_folder",
]
