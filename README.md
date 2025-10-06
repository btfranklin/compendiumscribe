# Compendium Scribe

[![Build Status](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml/badge.svg)](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml)
[![Supports Python versions 3.12+](https://img.shields.io/pypi/pyversions/compendiumscribe.svg)](https://pypi.python.org/pypi/compendiumscribe)

Compendium Scribe is a Click-driven command line tool and library that uses OpenAI's **deep research** models to assemble a highly structured XML compendium for any topic. The workflow combines optional prompt refinement (powered by `gpt-4.1`), an `o3-deep-research` call with web search tooling, and deterministic post-processing to turn the model output into a dependable knowledge asset.

---

## Features
- 🔍 **Deep research pipeline** — orchestrates prompt planning, background execution, and tool-call capture with `o3-deep-research`.
- 🧱 **Rich data model** — includes sections, insights, citations, and research trace metadata for auditing.
- 🧾 **Structured XML output** — produces a schema-friendly document ready for downstream conversion (HTML, Markdown, PDF pipelines, etc.).
- ⚙️ **Configurable CLI** — control background execution, tool call limits, and output paths.
- 🧪 **Testable architecture** — research orchestration is decoupled from the OpenAI client, making it simple to stub in tests.

---

## Quick Start

### 1. Install

```bash
pdm install --dev
```

Ensure `PDM_HOME` points to a writable location when developing within a sandboxed environment.

### 2. Configure credentials

Create a `.env` file (untracked) with your OpenAI credentials:

```
OPENAI_API_KEY=sk-...
```

Deep research requires an OpenAI account with the browsing tooling enabled. Document any environment keys for additional tooling in the repo as you add them.

### 3. Generate a compendium

```bash
pdm run create-compendium "Lithium-ion battery recycling"
```

Options:
- `--output PATH` — where to write the XML file (defaults to `<slug>_<timestamp>.xml`).
- `--no-background` — force synchronous execution (useful for short or restricted queries).
- `--max-tool-calls N` — cap the total number of tool calls for cost control.
- `--export-format FORMAT` — repeat to emit Markdown (`md`), HTML (`html`), or PDF (`pdf`) alongside the base XML output.

Example output file name: `lithium-ion-battery-recycling_20250107_143233.xml`.

---

## Library Usage

```python
from compendiumscribe import build_compendium, ResearchConfig, DeepResearchError

try:
    compendium = build_compendium(
        "Emerging pathogen surveillance",
        config=ResearchConfig(background=False, max_tool_calls=30),
    )
except DeepResearchError as exc:
    # Handle or log deep research failures
    raise

xml_payload = compendium.to_xml_string()

# Alternate exports
markdown_doc = compendium.to_markdown()
html_doc = compendium.to_html()
pdf_bytes = compendium.to_pdf_bytes()
```

The returned `Compendium` object contains structured sections, insights, citations, open questions, and the trace of tool calls used during research.

---

## Data Model Overview

Compendium Scribe produces XML shaped like:

```xml
<compendium topic="Lithium-ion Battery Recycling" generated_at="2025-01-07T14:32:33+00:00">
  <overview><![CDATA[Comprehensive synthesis of the state of lithium-ion recycling...]]></overview>
  <methodology>
    <step><![CDATA[Surveyed peer-reviewed literature from 2022–2025]]></step>
    <step><![CDATA[Corroborated industrial capacity data with regulatory filings]]></step>
  </methodology>
  <sections>
    <section id="S01">
      <title><![CDATA[Technology Landscape]]></title>
      <summary><![CDATA[Dominant recycling modalities and throughput metrics...]]></summary>
      <key_terms>
        <term><![CDATA[hydrometallurgy]]></term>
        <term><![CDATA[direct recycling]]></term>
      </key_terms>
      <guiding_questions>
        <question><![CDATA[Which processes yield the highest cobalt recovery rates?]]></question>
      </guiding_questions>
      <insights>
        <insight>
          <title><![CDATA[Hydrometallurgy remains the throughput leader]]></title>
          <evidence><![CDATA[EPRI 2024 data shows >95% cobalt recovery in commercial plants.]]></evidence>
          <implications><![CDATA[Capital efficiency favors hydrometallurgy for near-term scaling.]]></implications>
          <citations>
            <ref>C1</ref>
          </citations>
        </insight>
      </insights>
    </section>
  </sections>
  <citations>
    <citation id="C1">
      <title><![CDATA[EPRI Lithium-ion Recycling Benchmarking 2024]]></title>
      <url><![CDATA[https://example.com/epri-li-benchmark]]></url>
      <publisher><![CDATA[EPRI]]></publisher>
      <published_at><![CDATA[2024-09-01]]></published_at>
      <summary><![CDATA[Performance metrics for recycling modalities across 12 facilities.]]></summary>
    </citation>
  </citations>
  <open_questions>
    <question><![CDATA[How will policy incentives shape regional plant siting post-2025?]]></question>
  </open_questions>
  <research_trace>
    <trace_event id="ws_1" type="web_search_call" status="completed">
      <action>{"type": "search", "query": "lithium ion recycling throughput"}</action>
    </trace_event>
  </research_trace>
</compendium>
```

This format is intentionally verbose to support downstream transformation and provenance tracking.

---

## Testing & Quality

- `pdm run pytest` — executes the unit suite. Tests stub the OpenAI client, so they run offline.
- `pdm run flake8 src tests` — linting.
- `pdm build` — produce distributable artifacts.

If `pdm` fails to write log files in restricted environments, set `PDM_HOME` to a writable directory (for example, `export PDM_HOME=.pdm_home`).

---

## Contributing

1. Fork and clone the repository.
2. Run `pdm install --dev`.
3. Make changes following the style guide and update/add tests.
4. Run `pdm run pytest` and `pdm run flake8 src tests`.
5. Raise a pull request with:
   - A concise description of the change.
   - Verification commands executed locally.
   - Representative XML samples if the user-facing structure changes.

---

## License

MIT © B.T. Franklin and contributors.
