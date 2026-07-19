from __future__ import annotations

from unittest import mock
import os

from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.errors import MissingConfigurationError


def test_research_config_requires_contract_profile() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        try:
            ResearchConfig()
        except MissingConfigurationError as exc:
            message = str(exc)
        else:  # pragma: no cover - defensive failure clarity
            raise AssertionError("ResearchConfig accepted a missing profile.")

    assert "CONTRACT4AGENTS_PROFILE" in message


def test_research_config_rejects_blank_contract_profile() -> None:
    with mock.patch.dict(
        os.environ,
        {"CONTRACT4AGENTS_PROFILE": " \t"},
        clear=True,
    ):
        try:
            ResearchConfig()
        except MissingConfigurationError as exc:
            message = str(exc)
        else:  # pragma: no cover - defensive failure clarity
            raise AssertionError("ResearchConfig accepted a blank profile.")

    assert "CONTRACT4AGENTS_PROFILE" in message


def test_research_config_uses_contract_profile_env_selection() -> None:
    with mock.patch.dict(
        os.environ,
        {"CONTRACT4AGENTS_PROFILE": " production "},
    ):
        config = ResearchConfig()

    assert config.contract4agents_profile == "production"


def test_research_config_accepts_explicit_constructor_values() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        config = ResearchConfig(contract4agents_profile="production")

    assert config.contract4agents_profile == "production"
