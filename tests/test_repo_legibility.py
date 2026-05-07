from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_entrypoints_exist_and_route_to_docs() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

    assert "docs/ARCHITECTURE.md" in agents
    assert "docs/QUALITY.md" in agents
    assert "docs/RELEASING.md" in agents
    assert "ARCHITECTURE.md" in docs_index
    assert "QUALITY.md" in docs_index
    assert "RELEASING.md" in docs_index


def test_entrypoint_docs_name_required_research_model_settings() -> None:
    required_model_vars = [
        "PLANNER_AGENT_MODEL",
        "RESEARCH_AGENT_MODEL",
        "VERIFIER_AGENT_MODEL",
        "SYNTHESIS_AGENT_MODEL",
    ]
    checked_paths = [
        ROOT / "README.md",
        ROOT / ".env.example",
    ]

    missing: list[str] = []
    for path in checked_paths:
        content = path.read_text(encoding="utf-8")
        for var_name in required_model_vars:
            if var_name not in content:
                missing.append(f"{path.relative_to(ROOT)} missing {var_name}")

    assert not missing, (
        "Entry-point docs should show the required current research model "
        f"settings. Missing from: {missing}"
    )


def test_library_docs_reference_catalog() -> None:
    checked_paths = [
        ROOT / "AGENTS.md",
        ROOT / "README.md",
        ROOT / "docs" / "ARCHITECTURE.md",
        ROOT / "docs" / "QUALITY.md",
        ROOT / "docs" / "README.md",
    ]

    missing_catalog = [
        str(path.relative_to(ROOT))
        for path in checked_paths
        if "catalog.json" not in path.read_text(encoding="utf-8")
    ]
    assert not missing_catalog, (
        "Library-facing docs should point agents to catalog.json. "
        f"Missing from: {missing_catalog}"
    )
