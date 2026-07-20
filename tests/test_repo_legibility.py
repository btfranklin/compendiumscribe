from __future__ import annotations

from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values

from compendiumscribe.research.config import REQUIRED_PROFILE_ENV_VAR


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / "docs" / "README.md",
)
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


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
            str(target.relative_to(ROOT)) for target in targets if not target.exists()
        )
        for path, targets in resolved_by_entrypoint.items()
        if any(not target.exists() for target in targets)
    }
    assert not missing, f"Entry-point documentation has broken links: {missing}"

    agent_routes = resolved_by_entrypoint[ROOT / "AGENTS.md"]
    assert {ROOT / "README.md", ROOT / "docs" / "README.md"} <= agent_routes


def test_example_environment_covers_runtime_research_configuration() -> None:
    example = dotenv_values(ROOT / ".env.example")
    missing = (
        [] if example.get(REQUIRED_PROFILE_ENV_VAR) else [REQUIRED_PROFILE_ENV_VAR]
    )

    assert not missing, (
        f".env.example is missing required research model configuration: {missing}"
    )


def test_readme_routes_environment_setup_to_the_template() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "cp .env.example .env" in readme
    assert "Set `OPENAI_API_KEY` in `.env`." in readme


def test_generated_contract_bytecode_remains_ignored() -> None:
    bytecode_path = (
        "src/compendiumscribe/agent_contracts/generated/python/__pycache__/models.pyc"
    )

    result = subprocess.run(
        ["git", "check-ignore", "--quiet", bytecode_path],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0
