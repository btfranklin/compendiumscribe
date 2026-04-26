# Compendium Scribe

![Compendium Scribe banner](https://raw.githubusercontent.com/btfranklin/compendiumscribe/main/.github/social%20preview/compendiumscribe_social_preview.jpg "Compendium Scribe")

[![Build Status](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml/badge.svg)](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml) [![Supports Python versions 3.12+](https://img.shields.io/pypi/pyversions/compendiumscribe.svg)](https://pypi.python.org/pypi/compendiumscribe)

Compendium Scribe is a Click-driven command line tool and library that builds sourced research compendiums through a bounded OpenAI Agents SDK workflow. It decomposes a topic into planning, web research, verification, and synthesis stages, then renders the final `Compendium` as Markdown, XML, HTML, PDF, or an AI skill folder.

---

## Features

- **Agents SDK research workflow** - Runs planner, research manager, section researcher, verifier, and synthesis agents with structured Pydantic outputs.
- **Hosted web search where it belongs** - Enables web search for research manager, section research, and verification agents; planner and synthesis stay source-controlled.
- **Stable renderer contract** - Final agent output is validated and passed through the existing `Compendium.from_payload()` shape.
- **Citation ledger** - Deduplicates URLs, assigns citation IDs, tracks section usage, and rejects final citations that are not ledger-backed.
- **Recoverable sidecars** - Writes `<base>.research.json` after accepted artifacts and `<base>.costs.json` for usage/cost telemetry.
- **Local cost estimates** - Uses a checked-in pricing catalog for GPT-5.4 family token rates, long-context uplifts, and built-in tool call pricing when usage metadata is available.
- **Re-rendering** - Ingest existing XML compendiums to generate new output formats without re-running research.
- **Skill export** - Emits an AI agent skill folder with `SKILL.md` plus the compendium Markdown in `references/`.
- **Offline tests** - The workflow uses a runner adapter so tests can stub Agents SDK runs without live API calls.

---

## Quick Start

### 1. Install

```bash
pdm install --dev
```

Ensure `PDM_HOME` points to a writable location when developing within a sandboxed environment.

### 2. Configure credentials

Create a `.env` file (untracked) with your OpenAI credentials and optional model overrides:

```dotenv
OPENAI_API_KEY=sk-...
PLANNER_AGENT_MODEL=gpt-5.4
RESEARCH_AGENT_MODEL=gpt-5.4
VERIFIER_AGENT_MODEL=gpt-5.4
SYNTHESIS_AGENT_MODEL=gpt-5.4
MAX_AGENT_TURNS=12
SKILL_NAMER_MODEL=gpt-5.2
SKILL_WRITER_MODEL=gpt-5.2
```

The research workflow uses the OpenAI Agents SDK with hosted web search enabled on the manager, section, and verifier agents.

Cost reports use the local catalog in `src/compendiumscribe/research/data/pricing.standard.json`. The catalog currently covers standard GPT-5.4 family token pricing, GPT-5.4 long-context rates above the documented threshold, web search calls, and Responses API file search calls. If a model is missing from the catalog, token usage is still recorded and USD estimates are left unavailable.

### 3. Generate a compendium

```bash
pdm run compendium create "Lithium-ion battery recycling"
```

Options:

- `--output PATH` - Base path/filename for the output. The extension is ignored.
- `--format FORMAT` - Output format, defaulting to `md`. Available: `md`, `xml`, `html`, `pdf`, `skill`. Repeat for multiple outputs.

If you pass `--output report.md`, Compendium Scribe writes:

- `report.md` or the requested render formats
- `report.research.json`
- `report.costs.json`

Without `--output`, the base name is the slugified topic plus a UTC timestamp.

### 4. Recover a research run

Recovery resumes from the next incomplete stage in the sidecar state file:

```bash
pdm run compendium recover --input report.research.json
```

The recover command writes outputs using the same base path as the sidecar. For example, `report.research.json` renders to `report.md` when the stored format is Markdown.

### 5. Render formats from existing XML

```bash
pdm run compendium render my-topic.xml --format html
```

Options:

- `--format FORMAT` - Output format(s) to generate: `md`, `xml`, `html`, `pdf`, `skill`.
- `--output PATH` - Base path/filename for the output.

---

## Library Usage

```python
from compendiumscribe import build_compendium, ResearchConfig, DeepResearchError

try:
    compendium = build_compendium(
        "Emerging pathogen surveillance",
        config=ResearchConfig(
            research_agent_model="gpt-5.4",
            verifier_agent_model="gpt-5.4",
            synthesis_agent_model="gpt-5.4",
        ),
    )
except DeepResearchError:
    raise

xml_payload = compendium.to_xml_string()
markdown_doc = compendium.to_markdown()
html_files = compendium.to_html_site()
pdf_bytes = compendium.to_pdf_bytes()
```

The returned `Compendium` object contains structured sections, insights, citations, and open questions.

---

## Data Model Overview

Compendium Scribe produces XML shaped like:

```xml
<compendium topic="Lithium-ion Battery Recycling" generated_at="2026-04-23T14:32:33+00:00">
  <overview><![CDATA[Comprehensive synthesis of the state of lithium-ion recycling...]]></overview>
  <methodology>
    <step><![CDATA[Surveyed peer-reviewed literature and company disclosures.]]></step>
  </methodology>
  <sections>
    <section id="S01">
      <title><![CDATA[Technology Landscape]]></title>
      <summary><![CDATA[Dominant recycling modalities and throughput metrics...]]></summary>
      <insights>
        <insight>
          <title><![CDATA[Hydrometallurgy remains the throughput leader]]></title>
          <evidence><![CDATA[Commercial operators report high recovery rates for core battery metals.]]></evidence>
          <citations>
            <ref>C01</ref>
          </citations>
        </insight>
      </insights>
    </section>
  </sections>
  <citations>
    <citation id="C01">
      <title><![CDATA[Example Recycling Benchmark]]></title>
      <url><![CDATA[https://example.com/recycling-benchmark]]></url>
      <publisher><![CDATA[Example Publisher]]></publisher>
    </citation>
  </citations>
</compendium>
```

---

## Testing & Quality

- `pdm run test` - Executes the unit suite. Tests stub Agents SDK runs, so they run offline.
- `pdm run lint` - Linting.
- `pdm run ruff check src tests` - Direct lint command.
- `pdm build` - Produce distributable artifacts.

Before marking implementation work complete, run:

```bash
pdm run pytest
pdm run ruff check src tests
pdm build
```

---

## Contributing

1. Fork and clone the repository.
2. Run `pdm install --group dev`.
3. Make changes following the style guide and update/add tests.
4. Run `pdm run pytest`, `pdm run ruff check src tests`, and `pdm build`.
5. Raise a pull request with a concise description, verification commands, and representative output samples when user-facing structure changes.
