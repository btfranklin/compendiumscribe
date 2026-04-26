from __future__ import annotations

from unittest import mock
import os

from compendiumscribe.research.config import ResearchConfig


def test_research_config_defaults_to_gpt_5_4() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        config = ResearchConfig()

    assert config.planner_agent_model == "gpt-5.4"
    assert config.research_agent_model == "gpt-5.4"
    assert config.verifier_agent_model == "gpt-5.4"
    assert config.synthesis_agent_model == "gpt-5.4"


def test_research_config_uses_agent_model_env_overrides() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "PLANNER_AGENT_MODEL": "planner-model",
            "RESEARCH_AGENT_MODEL": "research-model",
            "VERIFIER_AGENT_MODEL": "verifier-model",
            "SYNTHESIS_AGENT_MODEL": "synthesis-model",
        },
    ):
        config = ResearchConfig()

    assert config.planner_agent_model == "planner-model"
    assert config.research_agent_model == "research-model"
    assert config.verifier_agent_model == "verifier-model"
    assert config.synthesis_agent_model == "synthesis-model"
