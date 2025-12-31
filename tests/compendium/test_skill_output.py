from __future__ import annotations

import json
from pathlib import Path

import pytest

from compendiumscribe.compendium import Compendium
from compendiumscribe.skill_output import (
    SkillConfig,
    SkillGenerationError,
    render_skill_folder,
)


class DummyResponses:
    def __init__(self, payloads: list[dict[str, str]]):
        self._payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._payloads:
            raise RuntimeError("No more responses configured.")
        return self._payloads.pop(0)


class DummyClient:
    def __init__(self, payloads: list[dict[str, str]]):
        self.responses = DummyResponses(payloads)


def _sample_compendium() -> Compendium:
    return Compendium(
        topic="Skill Output Test",
        overview="Overview text.",
    )


def test_render_skill_folder_writes_expected_files(tmp_path: Path):
    name_payload = {
        "name": "analyze-market-risks",
        "description": "Analyze market risks and provide mitigation advice.",
    }
    skill_markdown = (
        "---\n"
        "name: analyze-market-risks\n"
        "description: Analyze market risks and provide mitigation advice.\n"
        "---\n\n"
        "Read `references/report_20250101.md` before answering.\n"
    )
    payloads = [
        {"output_text": json.dumps(name_payload)},
        {"output_text": json.dumps({"skill_markdown": skill_markdown})},
    ]
    client = DummyClient(payloads)
    config = SkillConfig(max_retries=1)

    compendium = _sample_compendium()
    base_path = tmp_path / "report_20250101"
    skill_dir = render_skill_folder(
        compendium,
        base_path,
        client,
        config,
    )

    assert skill_dir == tmp_path / "analyze-market-risks"
    skill_file = skill_dir / "SKILL.md"
    reference_file = skill_dir / "references" / "report_20250101.md"

    assert skill_file.exists()
    assert skill_file.read_text(encoding="utf-8") == skill_markdown
    assert reference_file.exists()
    assert reference_file.read_text(encoding="utf-8") == (
        compendium.to_markdown()
    )


def test_render_skill_folder_retries_and_fails(tmp_path: Path):
    payloads = [
        {"output_text": "not json"},
        {"output_text": "still not json"},
    ]
    client = DummyClient(payloads)
    config = SkillConfig(max_retries=2)

    with pytest.raises(SkillGenerationError):
        render_skill_folder(
            _sample_compendium(),
            tmp_path / "output",
            client,
            config,
        )
