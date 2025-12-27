from __future__ import annotations

import os
from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_TIMEOUT_SECONDS = 3600


class MissingAPIKeyError(RuntimeError):
    """Raised when the OPENAI_API_KEY environment variable is absent."""


def create_openai_client(*, timeout: int | None = None) -> OpenAI:
    """Initialise the OpenAI client using environment configuration."""

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY missing; set via env or .env file."
        )

    # Use a default timeout if none specified to prevent indefinite hangs
    actual_timeout = (
        timeout
        if timeout is not None
        else DEFAULT_TIMEOUT_SECONDS
    )

    client = OpenAI(api_key=api_key, timeout=actual_timeout)

    # Quick sanity check for the required API capability
    if not hasattr(client, "responses"):
        raise RuntimeError(
            "Installed openai package does not expose the Responses API. "
            "Upgrade to a newer openai release (e.g. `pip install -U openai`)."
        )
    return client


__all__ = ["create_openai_client", "MissingAPIKeyError"]
