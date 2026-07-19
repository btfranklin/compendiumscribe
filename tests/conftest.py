import os
import pytest
from unittest import mock


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Automatically mock environment variables for all tests."""
    with mock.patch.dict(
        os.environ,
        {
            "CONTRACT4AGENTS_PROFILE": "production",
            "OPENAI_API_KEY": "sk-test",
        },
    ):
        yield
