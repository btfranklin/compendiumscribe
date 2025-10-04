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

    client_kwargs: dict[str, object] = {"api_key": api_key}
    client_kwargs["timeout"] = timeout or DEFAULT_TIMEOUT_SECONDS

    return OpenAI(**client_kwargs)


__all__ = ["create_openai_client", "MissingAPIKeyError"]
