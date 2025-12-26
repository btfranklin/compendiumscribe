from __future__ import annotations


class DeepResearchError(RuntimeError):
    """Raised when the deep research workflow cannot complete successfully."""


class MissingConfigurationError(RuntimeError):
    """Raised when required configuration is missing."""


class ResearchTimeoutError(DeepResearchError):
    """Raised when deep research exceeds the configured time limit."""

    def __init__(self, message: str, research_id: str):
        super().__init__(message)
        self.research_id = research_id


class ResearchCancelledError(DeepResearchError):
    """Raised when research is cancelled by user."""

    def __init__(self, message: str, research_id: str):
        super().__init__(message)
        self.research_id = research_id


__all__ = [
    "DeepResearchError",
    "MissingConfigurationError",
    "ResearchCancelledError",
    "ResearchTimeoutError",
]
