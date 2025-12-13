from __future__ import annotations

from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.errors import MissingConfigurationError
import pytest
import os
from unittest import mock


def test_research_config_raises_missing_config_error():
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(MissingConfigurationError):
            ResearchConfig()

def test_research_config_uses_env_override():
    with mock.patch.dict(os.environ, {
        "PROMPT_REFINER_MODEL": "custom-refiner",
        "DEEP_RESEARCH_MODEL": "custom-deep",
    }):
        config = ResearchConfig()
        assert config.prompt_refiner_model == "custom-refiner"
        assert config.deep_research_model == "custom-deep"
