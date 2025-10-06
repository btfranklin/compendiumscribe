from __future__ import annotations

from compendiumscribe.research.config import ResearchConfig


def test_research_config_uses_env_override(monkeypatch):
    monkeypatch.setenv("RESEARCH_MODEL", "custom-deep-model")

    config = ResearchConfig()

    assert config.deep_research_model == "custom-deep-model"
