from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from ...compendium import Compendium, slugify
from ..config import ResearchConfig
from ..errors import DeepResearchError
from ..progress import emit_progress
from .agents import (
    create_planner_agent,
    create_research_manager_agent,
    create_section_research_agent,
    create_synthesis_agent,
    create_verifier_agent,
)
from .artifacts import (
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    ResearchRunState,
    SectionResearchBrief,
    VerificationReport,
    prepare_compendium_payload,
)
from .costing import record_agent_result_cost
from .runner import AgentRunResult, AgentRunner, OpenAIAgentRunner
from .source_ledger import build_source_ledger, mark_cited_sources
from .state import load_state, save_state

if TYPE_CHECKING:
    from ..costs import CostTracker
    from openai import AsyncOpenAI

ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


def build_compendium_with_agents(
    topic: str,
    *,
    client: "AsyncOpenAI | None" = None,
    config: ResearchConfig | None = None,
    runner: AgentRunner | None = None,
    state_path: Path | None = None,
    cost_tracker: "CostTracker | None" = None,
    output_formats: list[str] | tuple[str, ...] = (),
) -> Compendium:
    if not topic or not topic.strip():
        raise ValueError("Topic must be a non-empty string.")

    config = config or ResearchConfig()
    runner = runner or OpenAIAgentRunner(openai_client=client)
    resolved_state_path = state_path or _default_state_path(topic.strip())

    try:
        return asyncio.run(
            _build_compendium_async(
                topic.strip(),
                config=config,
                runner=runner,
                state_path=resolved_state_path,
                cost_tracker=cost_tracker,
                output_formats=list(output_formats),
            )
        )
    except DeepResearchError:
        raise
    except Exception as exc:
        emit_progress(
            config,
            phase="completion",
            status="error",
            message=str(exc),
        )
        raise


def recover_compendium_from_state(
    state_path: Path,
    *,
    client: "AsyncOpenAI | None" = None,
    config: ResearchConfig | None = None,
    runner: AgentRunner | None = None,
    cost_tracker: "CostTracker | None" = None,
) -> Compendium:
    state = load_state(state_path)
    return build_compendium_with_agents(
        state.topic,
        client=client,
        config=config,
        runner=runner,
        state_path=state_path,
        cost_tracker=cost_tracker,
        output_formats=state.output_formats,
    )


async def _build_compendium_async(
    topic: str,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    state_path: Path,
    cost_tracker: "CostTracker | None",
    output_formats: list[str],
) -> Compendium:
    state = _load_or_create_state(
        topic=topic,
        state_path=state_path,
        output_formats=output_formats,
        cost_tracker=cost_tracker,
        config=config,
    )
    save_state(state_path, state)

    if state.plan is None:
        state.plan = await _run_structured_agent(
            "planning",
            create_planner_agent(config),
            _json_prompt({"topic": topic}),
            output_type=ResearchPlan,
            config=config,
            runner=runner,
            model=config.planner_agent_model,
            cost_tracker=cost_tracker,
            state=state,
        )
        state.title = state.plan.title
        state.mark_completed("planning")
        save_state(state_path, state)

    if state.agenda is None:
        state.agenda = await _run_structured_agent(
            "research_agenda",
            create_research_manager_agent(config),
            _json_prompt(
                {
                    "topic": topic,
                    "plan": state.plan.model_dump(mode="json"),
                }
            ),
            output_type=ResearchAgenda,
            config=config,
            runner=runner,
            model=config.research_agent_model,
            cost_tracker=cost_tracker,
            state=state,
        )
        state.mark_completed("research_agenda")
        save_state(state_path, state)

    await _run_missing_sections(
        state,
        config=config,
        runner=runner,
        cost_tracker=cost_tracker,
        state_path=state_path,
    )
    _rebuild_ledger(state)
    state.mark_completed("source_ledger")
    save_state(state_path, state)

    if state.verification is None:
        state.verification = await _verify(
            state,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
        )
        state.mark_completed("verification")
        save_state(state_path, state)

    if (
        state.verification.status == "follow_up"
        and not state.follow_up_done
    ):
        await _run_follow_up_sections(
            state,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            state_path=state_path,
        )
        _rebuild_ledger(state)
        state.follow_up_done = True
        state.verification = await _verify(
            state,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
        )
        state.mark_completed("verification_follow_up")
        save_state(state_path, state)

    if state.verification.status == "failed":
        save_state(state_path, state)
        raise DeepResearchError(_verification_failure_message(state))

    if state.final_payload is None:
        state.final_payload = await _run_structured_agent(
            "synthesis",
            create_synthesis_agent(config),
            _json_prompt(
                {
                    "topic": state.title or topic,
                    "plan": state.plan.model_dump(mode="json"),
                    "agenda": state.agenda.model_dump(mode="json"),
                    "section_briefs": [
                        brief.model_dump(mode="json")
                        for brief in state.section_briefs.values()
                    ],
                    "source_ledger": state.ledger.model_dump(mode="json"),
                    "verification": state.verification.model_dump(mode="json"),
                }
            ),
            output_type=CompendiumPayload,
            config=config,
            runner=runner,
            model=config.synthesis_agent_model,
            cost_tracker=cost_tracker,
            state=state,
        )
        state.final_payload = prepare_compendium_payload(
            state.final_payload, state.ledger
        )
        state.mark_completed("synthesis")
        save_state(state_path, state)
    else:
        prepared_payload = prepare_compendium_payload(
            state.final_payload, state.ledger
        )
        if prepared_payload != state.final_payload:
            state.final_payload = prepared_payload
            save_state(state_path, state)

    emit_progress(
        config,
        phase="completion",
        status="completed",
        message="Compendium payload is complete.",
        metadata={"state_path": str(state_path)},
    )
    return Compendium.from_payload(
        topic=state.title or topic,
        payload=state.final_payload.to_payload(),
        generated_at=datetime.now(timezone.utc),
    )


async def _run_missing_sections(
    state: ResearchRunState,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
) -> None:
    for section in state.agenda.sections:
        if section.id in state.section_briefs:
            continue
        state.section_briefs[section.id] = await _run_section_agent(
            section.id,
            state,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
        )
        state.mark_completed(f"section_research:{section.id}")
        save_state(state_path, state)


async def _run_follow_up_sections(
    state: ResearchRunState,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    state_path: Path,
) -> None:
    section_ids = list(dict.fromkeys(state.verification.follow_up_section_ids))
    for section_id in section_ids:
        if not _agenda_section(state, section_id):
            continue
        state.section_briefs[section_id] = await _run_section_agent(
            section_id,
            state,
            config=config,
            runner=runner,
            cost_tracker=cost_tracker,
            follow_up=True,
        )
        state.mark_completed(f"section_follow_up:{section_id}")
        save_state(state_path, state)


async def _run_section_agent(
    section_id: str,
    state: ResearchRunState,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
    follow_up: bool = False,
) -> SectionResearchBrief:
    section = _agenda_section(state, section_id)
    if section is None:
        raise DeepResearchError(f"Unknown agenda section: {section_id}")
    return await _run_structured_agent(
        "section_research",
        create_section_research_agent(config),
        _json_prompt(
            {
                "topic": state.title or state.topic,
                "section": section.model_dump(mode="json"),
                "plan": state.plan.model_dump(mode="json"),
                "agenda": state.agenda.model_dump(mode="json"),
                "previous_brief": (
                    state.section_briefs.get(section_id).model_dump(mode="json")
                    if follow_up and section_id in state.section_briefs
                    else None
                ),
                "verification": (
                    state.verification.model_dump(mode="json")
                    if follow_up and state.verification is not None
                    else None
                ),
            }
        ),
        output_type=SectionResearchBrief,
        config=config,
        runner=runner,
        model=config.research_agent_model,
        cost_tracker=cost_tracker,
        state=state,
        metadata={"section_id": section_id, "follow_up": follow_up},
    )


async def _verify(
    state: ResearchRunState,
    *,
    config: ResearchConfig,
    runner: AgentRunner,
    cost_tracker: "CostTracker | None",
):
    return await _run_structured_agent(
        "verification",
        create_verifier_agent(config),
        _json_prompt(
            {
                "topic": state.title or state.topic,
                "plan": state.plan.model_dump(mode="json"),
                "agenda": state.agenda.model_dump(mode="json"),
                "section_briefs": [
                    brief.model_dump(mode="json")
                    for brief in state.section_briefs.values()
                ],
                "source_ledger": state.ledger.model_dump(mode="json"),
                "follow_up_available": not state.follow_up_done,
            }
        ),
        output_type=VerificationReport,
        config=config,
        runner=runner,
        model=config.verifier_agent_model,
        cost_tracker=cost_tracker,
        state=state,
    )


async def _run_structured_agent(
    phase: str,
    agent: Any,
    input_payload: str,
    *,
    output_type: type[ArtifactT],
    config: ResearchConfig,
    runner: AgentRunner,
    model: str,
    cost_tracker: "CostTracker | None",
    state: ResearchRunState,
    metadata: dict[str, Any] | None = None,
) -> ArtifactT:
    emit_progress(
        config,
        phase=phase,
        status="in_progress",
        message=f"Running {getattr(agent, 'name', phase)}.",
        metadata=metadata,
    )
    result = await runner.run(
        agent,
        input_payload,
        max_turns=config.max_agent_turns,
    )
    record_agent_result_cost(
        cost_tracker,
        phase=phase,
        model=model,
        result=result,
    )
    state.response_ids[phase] = list(
        dict.fromkeys(state.response_ids.get(phase, []) + result.response_ids)
    )
    artifact = _coerce_artifact(result, output_type)
    emit_progress(
        config,
        phase=phase,
        status="completed",
        message=f"Accepted {getattr(agent, 'name', phase)} output.",
        metadata=metadata,
    )
    return artifact


def _coerce_artifact(
    result: AgentRunResult,
    output_type: type[ArtifactT],
) -> ArtifactT:
    output = result.final_output
    if isinstance(output, output_type):
        return output
    if isinstance(output, dict):
        return output_type.model_validate(output)
    if isinstance(output, str):
        return output_type.model_validate_json(output)
    return output_type.model_validate(output)


def _rebuild_ledger(state: ResearchRunState) -> None:
    briefs = list(state.section_briefs.values())
    ledger = build_source_ledger(briefs)
    cited_urls = [
        source_url
        for brief in briefs
        for finding in brief.findings
        for source_url in finding.source_urls
    ]
    state.ledger = mark_cited_sources(ledger, cited_urls)


def _load_or_create_state(
    *,
    topic: str,
    state_path: Path,
    output_formats: list[str],
    cost_tracker: "CostTracker | None",
    config: ResearchConfig,
) -> ResearchRunState:
    if state_path.exists():
        return load_state(state_path)
    return ResearchRunState(
        topic=topic,
        title=topic,
        output_formats=list(output_formats),
        cost_report_path=str(cost_tracker.path) if cost_tracker else None,
        config_snapshot=config.model_snapshot(),
    )


def _json_prompt(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _agenda_section(state: ResearchRunState, section_id: str):
    for section in state.agenda.sections:
        if section.id == section_id:
            return section
    return None


def _verification_failure_message(state: ResearchRunState) -> str:
    issues = state.verification.issues if state.verification else []
    details = "; ".join(issue.message for issue in issues) or "unspecified"
    return f"Research verification failed: {details}"


def _default_state_path(topic: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(f"{slugify(topic)}_{timestamp}.research.json")


__all__ = [
    "build_compendium_with_agents",
    "recover_compendium_from_state",
]
