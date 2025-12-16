from __future__ import annotations

import json

from compendiumscribe.research.config import ResearchConfig
from compendiumscribe.research.orchestrator import build_compendium


class FakeResponse:
    def __init__(
        self,
        *,
        output_text=None,
        output=None,
        status="completed",
        response_id="resp_1",
    ):
        self.output_text = output_text
        self.output = output or []
        self.status = status
        self.id = response_id


class FakeResponsesAPI:
    def __init__(self, plan_json: str, research_json: str):
        self.plan_json = plan_json
        self.research_json = research_json
        self.calls: list[dict[str, str]] = []

    def create(self, **kwargs):
        model = kwargs.get("model")
        self.calls.append(
            {"model": model, "input": kwargs.get("input", "")}
        )

        # Updated to match project defaults (e.g. gpt-5.2)
        if model in {"gpt-5.2", "gpt-4.1", "gpt-4.1-mini"}:
            return FakeResponse(
                output_text=self.plan_json,
                response_id="plan_1",
            )

        if model == "o3-deep-research":
            output = [
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "query": "quantum computing breakthroughs",
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": self.research_json,
                        }
                    ],
                },
            ]
            return FakeResponse(
                output=output,
                status="completed",
                response_id="research_1",
            )

        raise AssertionError(f"Unexpected model request: {model}")

    def retrieve(self, response_id: str):
        raise AssertionError(
            f"retrieve called unexpectedly for {response_id}"
        )


class FakeOpenAI:
    def __init__(self, plan_json: str, research_json: str):
        self.responses = FakeResponsesAPI(plan_json, research_json)


def test_build_compendium_with_stub_client():
    plan = {
        "primary_objective": "Build a comprehensive compendium",
        "audience": "Strategic leadership teams",
        "key_sections": [
            {"title": "Context", "focus": "Historical milestones"},
            {"title": "Applications", "focus": "Practical deployments"},
        ],
        "research_questions": [
            "What breakthroughs unlocked current capabilities?",
            "Who are the leading vendors?",
        ],
        "methodology_preferences": [
            "Verify each statistic using at least two sources",
            "Prioritize materials from 2022 onward",
        ],
    }

    research_payload = {
        "topic_overview": (
            "Quantum computing is transitioning from lab prototypes to early"
            " commercial pilots."
        ),
        "methodology": [
            "Surveyed public filings and analyst coverage",
            "Aggregated investment data across multiple trackers",
        ],
        "sections": [
            {
                "id": "S1",
                "title": "Technological Foundations",
                "summary": (
                    "Hardware approaches and error correction challenges"
                ),
                "key_terms": ["superconducting qubits"],
                "guiding_questions": [
                    "Which modalities show the most promise?"
                ],
                "insights": [
                    {
                        "title": (
                            "Superconducting qubits dominate near-term "
                            "roadmaps"
                        ),
                        "evidence": (
                            "IBM and Google published roadmaps targeting >1000"
                            " qubits with heavy error mitigation by 2025."
                        ),
                        "implications": (
                            "Vendor lock-in may increase as proprietary"
                            " control stacks mature."
                        ),
                        "citations": ["C1", "C2"],
                    }
                ],
            }
        ],
        "citations": [
            {
                "id": "C1",
                "title": "IBM Quantum Roadmap",
                "url": "https://example.com/ibm-roadmap",
                "publisher": "IBM",
                "published_at": "2023-12-01",
                "summary": "Targets for qubit scaling and error mitigation.",
            },
            {
                "id": "C2",
                "title": "Google Quantum AI Progress Update",
                "url": "https://example.com/google-qa",
                "publisher": "Google",
                "published_at": "2024-02-10",
                "summary": "Highlights on achieving reduced error rates.",
            },
        ],
        "open_questions": [
            "How will supply chains support dilution refrigerators at scale?"
        ],
    }

    client = FakeOpenAI(json.dumps(plan), json.dumps(research_payload))
    config = ResearchConfig(background=False)

    compendium = build_compendium(
        "Quantum Computing",
        client=client,
        config=config,
    )

    assert compendium.overview.startswith(
        "Quantum computing is transitioning"
    )
    assert compendium.sections[0].insights[0].citation_refs == ["C1", "C2"]
    assert (
        compendium.citations[1].title
        == "Google Quantum AI Progress Update"
    )
    assert not hasattr(compendium, "trace")
    assert len(client.responses.calls) == 2
    # The input is now a list of message objects
    research_input = client.responses.calls[1]["input"]
    assert isinstance(research_input, list)
    # Check if we can find the topic in the content of the user message.
    # The content structure varies (str or list of parts) depending on the source.
    # We perform a robust check against both formats.
    found = False
    for msg in research_input:
        content = msg.get("content", "")
        if isinstance(content, list):
            # It's a list of parts, e.g. [{"type": "input_text", "text": "..."}]
            for part in content:
                if "Quantum Computing" in part.get("text", ""):
                    found = True
                    break
        elif isinstance(content, str):
            if "Quantum Computing" in content:
                found = True
        
        if found:
            break
    
    assert found, "Topic not found in research call input"


def test_build_compendium_emits_progress_updates():
    plan = {"primary_objective": "Capture topic"}
    research_payload = {
        "topic_overview": "Overview",
        "methodology": [],
        "sections": [],
        "citations": [],
        "open_questions": [],
    }

    client = FakeOpenAI(json.dumps(plan), json.dumps(research_payload))
    captured: list = []

    def capture_progress(update):
        captured.append(update)

    config = ResearchConfig(
        background=False,
        progress_callback=capture_progress,
    )

    build_compendium("Test Topic", client=client, config=config)

    assert captured, "Expected progress callback to receive updates"
    phases = {event.phase for event in captured}
    assert "planning" in phases
    assert "deep_research" in phases
    assert any(event.status == "completed" for event in captured)
