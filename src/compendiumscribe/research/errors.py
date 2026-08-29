from __future__ import annotations

from pathlib import Path
from shlex import quote


class DeepResearchError(RuntimeError):
    """Raised when the research workflow cannot complete successfully."""


class MissingConfigurationError(RuntimeError):
    """Raised when required configuration is missing."""


class ResearchApprovalRequired(DeepResearchError):
    """Raised before a saved workflow starts paid follow-up research."""

    def __init__(self, state_path: Path, issue_codes: tuple[str, ...]) -> None:
        self.state_path = state_path
        self.issue_codes = issue_codes
        codes = ", ".join(issue_codes)
        super().__init__(
            "Paid follow-up research needs approval for issue(s) "
            f"{codes}. Run `pdm run compendium recover "
            f"--allow-paid-follow-up --input {quote(str(state_path))}` to approve one "
            "targeted research call."
        )


__all__ = [
    "DeepResearchError",
    "MissingConfigurationError",
    "ResearchApprovalRequired",
]
