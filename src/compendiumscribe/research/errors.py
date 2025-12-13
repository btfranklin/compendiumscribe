from __future__ import annotations


class DeepResearchError(RuntimeError):
    """Raised when the deep research workflow cannot complete successfully."""


class MissingConfigurationError(RuntimeError):
    """Raised when required configuration is missing."""


__all__ = ["DeepResearchError", "MissingConfigurationError"]
