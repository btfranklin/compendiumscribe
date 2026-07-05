from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from contract4agents.adapters.openai import plan_openai_agents_from_contracts
from contract4agents.cli import main as contract4agents_cli
from contract4agents.compiler import compile_project

from compendiumscribe.research.agents_workflow.agents import _load_prompt
from compendiumscribe.research.agents_workflow.artifacts import (
    CompendiumPayload,
    ResearchAgenda,
    ResearchPlan,
    SectionResearchBrief,
    VerificationReport,
)


CONTRACT_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "compendiumscribe"
    / "agent_contracts"
)


def test_agent_contracts_compile_with_python_models() -> None:
    artifacts = compile_project(CONTRACT_ROOT, allow_python_imports=True)

    assert set(artifacts["manifests"]) == {
        "PlannerAgent",
        "ResearchManagerAgent",
        "SectionResearchAgent",
        "VerifierAgent",
        "SynthesisAgent",
    }
    assert {item["name"] for item in artifacts["run_specs"]} == {
        "CompendiumResearch"
    }


def test_agent_contracts_pass_strict_drift_check() -> None:
    result = CliRunner().invoke(
        contract4agents_cli,
        [
            "check",
            str(CONTRACT_ROOT),
            "--allow-python-imports",
            "--strict-drift",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Contract4Agents check passed" in result.output


def test_openai_adapter_plan_matches_research_agent_contracts() -> None:
    artifacts = compile_project(CONTRACT_ROOT, allow_python_imports=True)
    plan = plan_openai_agents_from_contracts(
        artifacts,
        output_type_registry={
            "CompendiumPayload": CompendiumPayload,
            "ResearchAgenda": ResearchAgenda,
            "ResearchPlan": ResearchPlan,
            "SectionResearchBrief": SectionResearchBrief,
            "VerificationReport": VerificationReport,
        },
        model_registry={
            "PlannerAgent": "planner-model",
            "ResearchManagerAgent": "research-model",
            "SectionResearchAgent": "research-model",
            "VerifierAgent": "verifier-model",
            "SynthesisAgent": "synthesis-model",
        },
        hosted_tool_registry={"openai.web_search": object()},
        instruction_overrides={
            "PlannerAgent": _load_prompt("planner_agent.prompt.md"),
            "ResearchManagerAgent": _load_prompt("research_manager_agent.prompt.md"),
            "SectionResearchAgent": _load_prompt("section_research_agent.prompt.md"),
            "VerifierAgent": _load_prompt("verifier_agent.prompt.md"),
            "SynthesisAgent": _load_prompt("synthesis_agent.prompt.md"),
        },
    )

    assert plan.caveats == []
    assert set(plan.agents) == {
        "PlannerAgent",
        "ResearchManagerAgent",
        "SectionResearchAgent",
        "VerifierAgent",
        "SynthesisAgent",
    }
    assert {
        agent_name: agent_plan.hosted_tools[0].config
        for agent_name, agent_plan in plan.agents.items()
        if agent_plan.hosted_tools
    } == {
        "ResearchManagerAgent": {"context_size": "medium"},
        "SectionResearchAgent": {"context_size": "high"},
        "VerifierAgent": {"context_size": "medium"},
    }
    assert plan.agents["PlannerAgent"].hosted_tools == []
    assert plan.agents["SynthesisAgent"].hosted_tools == []
    assert plan.agents["PlannerAgent"].instructions == _load_prompt(
        "planner_agent.prompt.md"
    )

