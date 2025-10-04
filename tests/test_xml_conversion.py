import json
import xml.etree.ElementTree as ET

from compendiumscribe.model import (
    Citation,
    Compendium,
    Insight,
    ResearchTraceEvent,
    Section,
    etree_to_string,
)
from compendiumscribe.research_domain import ResearchConfig, build_compendium


def test_compendium_to_xml_contains_expected_structure():
    compendium = Compendium(
        topic="Quantum Computing",
        overview="High-level synthesis",
        methodology=["Map core concepts", "Cross-validate findings"],
        sections=[
            Section(
                identifier="S1",
                title="Foundations",
                summary="Qubits and quantum gates",
                key_terms=["qubit", "superposition"],
                guiding_questions=["What distinguishes qubits from classical bits?"],
                insights=[
                    Insight(
                        title="Coherence is fragile",
                        evidence="Most systems retain coherence for microseconds before error correction overwhelms throughput.",
                        implications="Large-scale machines require aggressive error mitigation.",
                        citation_refs=["C1"],
                    )
                ],
            )
        ],
        citations=[
            Citation(
                identifier="C1",
                title="A Survey on Quantum Error Correction",
                url="https://example.com/qec",
                publisher="ACM",
                published_at="2023-04-01",
                summary="Overview of leading quantum error correction strategies.",
            )
        ],
        open_questions=["When will logical qubits exceed 100 by default?"],
        trace=[
            ResearchTraceEvent(
                event_id="ws_1",
                event_type="web_search_call",
                status="completed",
                action={"query": "latest quantum error correction breakthroughs"},
            )
        ],
    )

    xml_string = compendium.to_xml_string()
    root = ET.fromstring(xml_string)

    assert root.tag == "compendium"
    assert root.attrib["topic"] == "Quantum Computing"
    assert root.findtext("overview") == "High-level synthesis"
    assert root.find("sections/section/title").text == "Foundations"
    assert root.find("citations/citation/title").text == "A Survey on Quantum Error Correction"
    assert root.find("research_trace/trace_event").attrib["id"] == "ws_1"


def test_compendium_from_payload_normalises_fields():
    payload = {
        "topic_overview": "A concise overview",
        "methodology": ["Collect expert commentary", "Highlight quantitative indicators"],
        "sections": [
            {
                "id": "S1",
                "title": "Key Dynamics",
                "summary": "Market movements and investment levels",
                "key_terms": ["capex"],
                "guiding_questions": ["Which regions are scaling fastest?"],
                "insights": [
                    {
                        "title": "Private investment surged",
                        "evidence": "Funding grew 45% year over year according to PitchBook.",
                        "implications": "Competition for talent is increasing.",
                        "citations": ["C1"],
                    }
                ],
            }
        ],
        "citations": [
            {
                "id": "C1",
                "title": "PitchBook Emerging Tech Report",
                "url": "https://example.com/pitchbook",
                "publisher": "PitchBook",
                "published_at": "2024-01-15",
                "summary": "Investment trends across quantum startups.",
            }
        ],
        "open_questions": ["How will regulation shape deployment?"],
        "trace": [
            {
                "id": "ws_1",
                "type": "web_search_call",
                "status": "completed",
                "action": {"query": "quantum funding 2024"},
            }
        ],
    }

    compendium = Compendium.from_payload("Quantum Capital", payload)

    assert compendium.topic == "Quantum Capital"
    assert compendium.methodology[0] == "Collect expert commentary"
    assert compendium.sections[0].insights[0].citation_refs == ["C1"]
    assert compendium.citations[0].publisher == "PitchBook"
    assert compendium.open_questions == ["How will regulation shape deployment?"]
    assert compendium.trace[0].event_id == "ws_1"


class FakeResponse:
    def __init__(self, *, output_text=None, output=None, status="completed", response_id="resp_1"):
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
        self.calls.append({"model": model, "input": kwargs.get("input", "")})

        if model in {"gpt-4.1", "gpt-4.1-mini"}:
            return FakeResponse(output_text=self.plan_json, response_id="plan_1")

        if model == "o3-deep-research":
            output = [
                {
                    "type": "web_search_call",
                    "id": "ws_1",
                    "status": "completed",
                    "action": {"type": "search", "query": "quantum computing breakthroughs"},
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
            return FakeResponse(output=output, status="completed", response_id="research_1")

        raise AssertionError(f"Unexpected model request: {model}")

    def retrieve(self, response_id: str):  # pragma: no cover - not exercised in this test
        raise AssertionError(f"retrieve called unexpectedly for {response_id}")


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
            "Prioritise materials from 2022 onward",
        ],
    }

    research_payload = {
        "topic_overview": "Quantum computing is transitioning from lab prototypes to early commercial pilots.",
        "methodology": [
            "Surveyed public filings and analyst coverage",
            "Aggregated investment data across multiple trackers",
        ],
        "sections": [
            {
                "id": "S1",
                "title": "Technological Foundations",
                "summary": "Hardware approaches and error correction challenges",
                "key_terms": ["superconducting qubits"],
                "guiding_questions": ["Which modalities show the most promise?"],
                "insights": [
                    {
                        "title": "Superconducting qubits dominate near-term roadmaps",
                        "evidence": "IBM and Google published roadmaps targeting >1000 qubits with heavy error mitigation by 2025.",
                        "implications": "Vendor lock-in may increase as proprietary control stacks mature.",
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
        "open_questions": ["How will supply chains support dilution refrigerators at scale?"],
    }

    client = FakeOpenAI(json.dumps(plan), json.dumps(research_payload))
    config = ResearchConfig(background=False)

    compendium = build_compendium("Quantum Computing", client=client, config=config)

    assert compendium.overview.startswith("Quantum computing is transitioning")
    assert compendium.sections[0].insights[0].citation_refs == ["C1", "C2"]
    assert compendium.citations[1].title == "Google Quantum AI Progress Update"
    assert compendium.trace[0].event_type == "web_search_call"
    assert len(client.responses.calls) == 2
    assert "Quantum Computing" in client.responses.calls[1]["input"]


def test_compendium_from_payload_generates_event_id_when_missing():
    payload = {
        "topic_overview": "Overview",
        "sections": [],
        "citations": [],
        "trace": [
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {"query": "test"},
            }
        ],
    }

    compendium = Compendium.from_payload("Topic", payload)

    assert compendium.trace[0].event_id.startswith("event-")


def test_etree_to_string_preserves_cdata_when_requested():
    root = ET.Element("note")
    content = ET.SubElement(root, "content")
    content.text = "Important <data>"

    xml = etree_to_string(root, cdata_tags={"content"})

    assert "<![CDATA[Important <data>]]>" in xml
