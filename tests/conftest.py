import os
import pytest
from unittest import mock


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Automatically mock environment variables for all tests."""
    with mock.patch.dict(os.environ, {
        "PROMPT_REFINER_MODEL": "gpt-5.2",
        "DEEP_RESEARCH_MODEL": "o3-deep-research",
        "OPENAI_API_KEY": "sk-test",
    }):
        yield
