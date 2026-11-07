"""Keep the validated draft and publication event boundaries aligned."""

from pathlib import Path

import yaml


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _workflow(name: str) -> dict:
    # BaseLoader preserves GitHub's `on` key rather than treating it as a bool.
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


def test_tag_draft_waits_for_the_full_ordinary_ci_matrix() -> None:
    draft = _workflow("create-draft-release.yml")
    assert draft["on"] == {"push": {"tags": ["v*.*.*"]}}
    validation = draft["jobs"]["validate"]
    assert validation["uses"] == "./.github/workflows/python-package.yml"
    ci = _workflow("python-package.yml")
    assert "workflow_call" in ci["on"]
    build = ci["jobs"]["build"]
    assert build["strategy"]["matrix"]["python-version"] == [
        "3.12", "3.13", "3.14"
    ]
    commands = "\n".join(step.get("run", "") for step in build["steps"])
    assert "pdm lock --check" in commands
    assert "pdm run check\n" in commands
    assert "pdm run check-dist dist" in commands
    release = draft["jobs"]["draft-release"]
    assert release["needs"] == "validate"
    assert "if" not in release
    scribe = next(
        step for step in release["steps"]
        if step.get("uses", "").startswith("btfranklin/release-notes-scribe@")
    )
    assert scribe["with"]["draft"] == "true"
    assert scribe["with"]["create_release"] == "true"


def test_publisher_only_rebuilds_the_release_tag_and_publishes() -> None:
    workflow = _workflow("python-publish.yml")
    assert workflow["on"] == {"release": {"types": ["published"]}}
    assert set(workflow["jobs"]) == {"publish"}
    publish = workflow["jobs"]["publish"]
    assert publish["environment"] == "release"
    assert publish["permissions"]["id-token"] == "write"
    steps = publish["steps"]
    checkout = steps[0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["ref"] == "${{ github.event.release.tag_name }}"
    assert checkout["with"]["fetch-depth"] == "0"
    assert [step["run"] for step in steps if "run" in step] == ["pdm build"]
    assert [step["uses"].split("@")[0] for step in steps if "uses" in step] == [
        "actions/checkout",
        "actions/setup-python",
        "pdm-project/setup-pdm",
        "pypa/gh-action-pypi-publish",
    ]
