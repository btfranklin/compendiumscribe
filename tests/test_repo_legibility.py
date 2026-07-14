from __future__ import annotations

from io import StringIO
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values

from compendiumscribe.research.config import REQUIRED_MODEL_ENV_VARS


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / "docs" / "README.md",
)
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")
DOTENV_BLOCK = re.compile(r"```dotenv\s*\n(.*?)\n```", re.DOTALL)


def _resolved_local_links(path: Path) -> set[Path]:
    destinations = MARKDOWN_LINK.findall(path.read_text(encoding="utf-8"))
    return {
        (path.parent / unquote(parsed.path)).resolve()
        for destination in destinations
        if not (parsed := urlsplit(destination)).scheme
        and not parsed.netloc
        and parsed.path
    }


def test_agent_entrypoints_route_to_resolvable_docs() -> None:
    resolved_by_entrypoint = {
        path: _resolved_local_links(path) for path in ENTRYPOINT_DOCS
    }

    unrouted = [
        str(path.relative_to(ROOT))
        for path, targets in resolved_by_entrypoint.items()
        if not targets
    ]
    assert not unrouted, f"Entry-point documentation has no local routes: {unrouted}"

    missing = {
        str(path.relative_to(ROOT)): sorted(
            str(target.relative_to(ROOT))
            for target in targets
            if not target.exists()
        )
        for path, targets in resolved_by_entrypoint.items()
        if any(not target.exists() for target in targets)
    }
    assert not missing, f"Entry-point documentation has broken links: {missing}"

    agent_routes = resolved_by_entrypoint[ROOT / "AGENTS.md"]
    assert {ROOT / "README.md", ROOT / "docs" / "README.md"} <= agent_routes


def test_example_environment_covers_runtime_research_configuration() -> None:
    example = dotenv_values(ROOT / ".env.example")
    required_names = {env_name for _, env_name in REQUIRED_MODEL_ENV_VARS}

    missing = sorted(name for name in required_names if not example.get(name))

    assert not missing, (
        ".env.example is missing required research model configuration: "
        f"{missing}"
    )


def test_readme_environment_example_matches_env_template() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = DOTENV_BLOCK.search(readme)

    assert match is not None, "README.md should include a dotenv example."

    readme_example = dotenv_values(stream=StringIO(match.group(1)))
    env_template = dotenv_values(ROOT / ".env.example")

    assert readme_example == env_template, (
        "README.md environment example must match .env.example."
    )
