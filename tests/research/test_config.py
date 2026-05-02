from __future__ import annotations

from unittest import mock
import os

from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.errors import MissingConfigurationError


def test_research_config_requires_agent_models() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        try:
            ResearchConfig()
        except MissingConfigurationError as exc:
            message = str(exc)
        else:  # pragma: no cover - defensive failure clarity
            raise AssertionError("ResearchConfig accepted missing models.")

    assert "PLANNER_AGENT_MODEL" in message
    assert "RESEARCH_AGENT_MODEL" in message
    assert "VERIFIER_AGENT_MODEL" in message
    assert "SYNTHESIS_AGENT_MODEL" in message


def test_research_config_rejects_blank_agent_models() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "PLANNER_AGENT_MODEL": "planner-model",
            "RESEARCH_AGENT_MODEL": " ",
            "VERIFIER_AGENT_MODEL": "\t",
            "SYNTHESIS_AGENT_MODEL": "synthesis-model",
        },
        clear=True,
    ):
        try:
            ResearchConfig()
        except MissingConfigurationError as exc:
            message = str(exc)
        else:  # pragma: no cover - defensive failure clarity
            raise AssertionError("ResearchConfig accepted blank models.")

    assert "RESEARCH_AGENT_MODEL" in message
    assert "VERIFIER_AGENT_MODEL" in message
    assert "PLANNER_AGENT_MODEL" not in message
    assert "SYNTHESIS_AGENT_MODEL" not in message


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


def test_research_config_accepts_explicit_constructor_values() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        config = ResearchConfig(
            planner_agent_model="planner-model",
            research_agent_model="research-model",
            verifier_agent_model="verifier-model",
            synthesis_agent_model="synthesis-model",
        )

    assert config.planner_agent_model == "planner-model"
    assert config.research_agent_model == "research-model"
    assert config.verifier_agent_model == "verifier-model"
    assert config.synthesis_agent_model == "synthesis-model"
