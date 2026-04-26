import os
import pytest
from unittest import mock


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Automatically mock environment variables for all tests."""
    with mock.patch.dict(os.environ, {
        "PLANNER_AGENT_MODEL": "gpt-5.4",
        "RESEARCH_AGENT_MODEL": "gpt-5.4",
        "VERIFIER_AGENT_MODEL": "gpt-5.4",
        "SYNTHESIS_AGENT_MODEL": "gpt-5.4",
        "OPENAI_API_KEY": "sk-test",
    }):
        yield
