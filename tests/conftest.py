import pytest


@pytest.fixture(autouse=True)
def default_research_model_env(monkeypatch):
    """Ensure tests default to the legacy deep-research model."""

    monkeypatch.setenv("RESEARCH_MODEL", "o3-deep-research")
