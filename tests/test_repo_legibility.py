from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_entrypoints_exist_and_route_to_docs() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert "docs/ARCHITECTURE.md" in agents
    assert "docs/QUALITY.md" in agents
    assert "ARCHITECTURE.md" in docs_index
    assert "QUALITY.md" in docs_index


def test_entrypoint_docs_do_not_reference_removed_research_runtime() -> None:
    stale_terms = [
        "DEEP_RESEARCH_MODEL",
        "PROMPT_REFINER_MODEL",
        "o3-deep-research",
        "--no-background",
        "--max-tool-calls",
        "timed_out_research.json",
        "topic_blueprint",
        "deep_research_assignment",
    ]
    checked_paths = [
        ROOT / "AGENTS.md",
        ROOT / "README.md",
        ROOT / ".env.example",
    ]

    offenders: list[str] = []
    for path in checked_paths:
        content = path.read_text(encoding="utf-8")
        for term in stale_terms:
            if term in content:
                offenders.append(f"{path.relative_to(ROOT)} contains {term}")

    assert not offenders, (
        "Entry-point docs reference removed Phase 1 research runtime terms. "
        "Update AGENTS.md, README.md, and .env.example to describe the "
        f"Agents SDK workflow instead. Offenders: {offenders}"
    )
