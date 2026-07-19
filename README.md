# Compendium Scribe

![Compendium Scribe banner](https://raw.githubusercontent.com/btfranklin/compendiumscribe/main/.github/social%20preview/compendiumscribe_social_preview.jpg "Compendium Scribe")

[![Build Status](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml/badge.svg)](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml) [![Supports Python versions 3.12+](https://img.shields.io/pypi/pyversions/compendiumscribe.svg)](https://pypi.python.org/pypi/compendiumscribe)

Compendium Scribe is a Click-driven command line tool and library that builds sourced research compendiums through a bounded OpenAI Agents SDK workflow. It decomposes a topic into planning, web research, verification, and synthesis stages, then renders the final `Compendium` as Markdown, XML, HTML, or PDF.

---

## Features

- **Agents SDK research workflow** - Runs planner, research manager, section researcher, verifier, and synthesis agents with structured Pydantic outputs.
- **Contracts as code** - Materializes the complete Agents SDK graph from packaged Contract4Agents source, target bindings, and the selected runtime model profile.
- **Generated portable models** - Generates the Pydantic models used by the application, plus TypeScript and Zod bindings, from the canonical contract types.
- **Hosted web search where it belongs** - Enables web search for research manager, section research, and verification agents; planner and synthesis stay source-controlled.
- **Stable renderer contract** - Final agent output is validated and passed through the existing `Compendium.from_payload()` shape.
- **Citation ledger** - Deduplicates URLs, assigns citation IDs, tracks section usage, and rejects final citations that are not ledger-backed.
- **Contract-bound traces** - Writes normalized trace evidence carrying the exact contract and materialization-plan digests, then assesses required controls before rendering.
- **Fail-closed capability evidence** - Rejects provider tool calls that do not resolve to an enabled grant in the materialization plan.
- **Recoverable sidecars** - Atomically writes `<base>.research.json` after accepted artifacts and `<base>.research.trace.jsonl` for normalized assurance evidence, alongside `<base>.costs.json` usage/cost telemetry.
- **Local cost estimates** - Uses a checked-in pricing catalog for GPT-5.5 and GPT-5.4 family token rates, long-context uplifts, and built-in tool call pricing when usage metadata is available.
- **Compendium Library publishing** - Optionally publishes XML, Markdown, and metadata cards into a movable filesystem library with a root `catalog.json`.
- **Re-rendering** - Ingest existing XML compendiums to generate new output formats without re-running research.
- **Offline tests** - The workflow uses a runner adapter so tests can stub Agents SDK runs without live API calls.

---

## Quick Start

### 1. Install

```bash
pdm install --dev
```

Ensure `PDM_HOME` points to a writable location when developing within a sandboxed environment.

### 2. Configure credentials

Create a `.env` file (untracked) with your OpenAI credentials and explicit research model settings:

```dotenv
OPENAI_API_KEY=sk-...
PLANNER_AGENT_MODEL=gpt-5.5
RESEARCH_AGENT_MODEL=gpt-5.5
VERIFIER_AGENT_MODEL=gpt-5.5
SYNTHESIS_AGENT_MODEL=gpt-5.5
MAX_AGENT_TURNS=12
```

All four model variables are required and supply the complete runtime model profile. If any are missing or blank, Compendium Scribe stops before client setup, cost report initialization, or research begins and names the missing setting. The packaged Contract4Agents target file owns provider and tool bindings, not model defaults.

The research workflow uses the OpenAI Agents SDK with hosted web search enabled on the manager, section, and verifier agents.

Cost reports use the local catalog in `src/compendiumscribe/research/data/pricing.standard.json`. The catalog currently covers GPT-5.5, GPT-5.4 family token pricing, long-context rates above the documented threshold, web search calls, and Responses API file search calls. If a model is missing from the catalog, token usage is still recorded and USD estimates are left unavailable.

### 3. Generate a compendium

```bash
pdm run compendium create "Lithium-ion battery recycling"
```

Options:

- `--output PATH` - Base path/filename for the output. The extension is ignored.
- `--format FORMAT` - Output format, defaulting to `md`. Available: `md`, `xml`, `html`, `pdf`. Repeat for multiple outputs.
- `--library PATH` - Also publish the finished compendium into a Compendium Library directory.

If you pass `--output report.md`, Compendium Scribe writes:

- `report.md` or the requested render formats
- `report.research.json`
- `report.research.trace.jsonl`
- `report.costs.json`

Without `--output`, the base name is the slugified topic plus a UTC timestamp.

### 4. Publish to a Compendium Library

A Compendium Library is a directory agents can scan progressively. The root
`catalog.json` is the compact card catalog. Each entry points to canonical XML,
readable Markdown, and a richer card for one compendium:

```text
research-library/
├── catalog.json
└── compendiums/
    └── lithium-ion-battery-recycling/
        ├── compendium.xml
        ├── compendium.md
        └── card.json
```

Creation works the same as usual unless `--library` is provided. When it is
provided, requested outputs are still written normally, and the final compendium
is also upserted into the library:

```bash
pdm run compendium create "Lithium-ion battery recycling" \
  --output report.md \
  --format md \
  --format xml \
  --library research-library
```

Import an existing XML compendium:

```bash
pdm run compendium library import research-library report.xml
```

Library entries are idempotent by slugified title. Re-publishing the same title
updates the existing `compendium.xml`, `compendium.md`, `card.json`, and
`catalog.json` entry. If another title would use the same slug, the new entry
gets a numeric suffix such as `-2`.

### 5. Recover a research run

Recovery resumes from the next incomplete stage in the sidecar state file:

```bash
pdm run compendium recover --input report.research.json
```

The recover command writes outputs using the same base path as the sidecar. For example, `report.research.json` renders to `report.md` when the stored format is Markdown.
Recovery appends to the matching normalized trace only when its contract and plan digests still match. Any sidecar containing accepted workflow progress requires a readable, nonempty trace; only a pristine `created` sidecar may start without one. Every completed recovery is reassessed against the same materialization plan and required controls before rendering.

### 6. Render formats from existing XML

```bash
pdm run compendium render my-topic.xml --format html
```

Options:

- `--format FORMAT` - Output format(s) to generate: `md`, `xml`, `html`, `pdf`.
- `--output PATH` - Base path/filename for the output.

---

## Python API Usage

```python
from compendiumscribe import build_compendium, ResearchConfig, DeepResearchError

try:
    compendium = build_compendium(
        "Emerging pathogen surveillance",
        config=ResearchConfig(
            planner_agent_model="gpt-5.5",
            research_agent_model="gpt-5.5",
            verifier_agent_model="gpt-5.5",
            synthesis_agent_model="gpt-5.5",
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
- `pdm run check` - Runs tests, linting, and package build.
- `pdm run ruff check src tests` - Direct lint command.
- `pdm build` - Produce distributable artifacts.

Before marking implementation work complete, run:

```bash
pdm run check
```

`pdm run check` runs the full required loop:

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
4. Run `pdm run check`.
5. Raise a pull request with a concise description, verification commands, and representative output samples when user-facing structure changes.
