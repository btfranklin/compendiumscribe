# Compendium Scribe

![Compendium Scribe banner](https://raw.githubusercontent.com/btfranklin/compendiumscribe/main/.github/social%20preview/compendiumscribe_social_preview.jpg "Compendium Scribe")

[![Build Status](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml/badge.svg)](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml) [![Supports Python versions 3.12+](https://img.shields.io/pypi/pyversions/compendiumscribe.svg)](https://pypi.python.org/pypi/compendiumscribe)

Compendium Scribe is a Click-driven command line tool and library that uses OpenAI's **deep research** models to assemble a comprehensive research compendium for any topic. The workflow combines optional prompt refinement, a "deep research" call with web search tooling, and deterministic post-processing. It produces human-readable Markdown by default, backed by a rich XML data model that can also be exported.

---

## Features

- 🔍 **Deep research pipeline** — Orchestrates prompt planning, background execution, and tool-call capture with `o3-deep-research`.
- 🧱 **Rich data model** — Includes sections, insights, and citations for cross-format rendering.
- 🧾 **Structured XML output** — Produces a schema-friendly document ready for downstream conversion (HTML, Markdown, PDF pipelines, etc.).
- 🌐 **HTML Site Export** — Generates a static, multi-page HTML site with navigation and semantic structure.
- 🔄 **Re-rendering** — Ingest existing XML compendiums to generate new output formats without re-running costly research.
- ⚙️ **Configurable CLI** — Control background execution, tool call limits, and output paths via a unified command structure.
- 🧪 **Testable architecture** — Research orchestration is decoupled from the OpenAI client, making it simple to stub in tests.

---

## Quick Start

### 1. Install

```bash
pdm install --group dev
```

Ensure `PDM_HOME` points to a writable location when developing within a sandboxed environment.

### 2. Configure credentials

Create a `.env` file (untracked) with your OpenAI credentials:

```
OPENAI_API_KEY=sk-...
PROMPT_REFINER_MODEL=gpt-5.2
DEEP_RESEARCH_MODEL=o3-deep-research
POLLING_INTERVAL_IN_SECONDS=10
MAX_POLL_TIME_IN_MINUTES=60
```

Deep research requires an OpenAI account with the browsing tooling enabled. Document any environment keys for additional tooling in the repo as you add them.

### 3. Generate a compendium

Use the `create` subcommand to verify a topic and run the research process:

```bash
pdm run compendium create "Lithium-ion battery recycling"
```

**Options:**
- `--output PATH` — Base path/filename for the output (extension is ignored).
- `--no-background` — Force synchronous execution (useful for short or restricted queries).
- `--max-tool-calls N` — Cap the total number of tool calls for cost control.
- `--format FORMAT` — Output format (defaults to `md`). Available: `md`, `xml`, `html`, `pdf`. Can be repeated for multiple outputs.

Example output file name: `lithium-ion-battery-recycling.md`.

### 4. Render formats from existing XML

If you have an existing XML compendium (e.g., `my-topic.xml`), you can re-render it into other formats:

```bash
pdm run compendium render my-topic.xml --format html
```

**Options:**
- `--format FORMAT` — Output format(s) to generate (`md`, `xml`, `html`, `pdf`).
- `--output PATH` — Base path/filename for the output.

### 5. Recover from a timeout

If a research task times out (exceeding `MAX_POLL_TIME_IN_MINUTES`), recovery information is saved to `timed_out_research.json`. You can resume checking for its completion without starting over:

```bash
pdm run compendium recover
```

**Options:**
- `--input PATH` — Path to the recovery JSON file (defaults to `timed_out_research.json`).

---

## Library Usage

```python
from compendiumscribe import build_compendium, ResearchConfig, DeepResearchError

try:
    compendium = build_compendium(
        "Emerging pathogen surveillance",
        config=ResearchConfig(
            background=False, 
            max_tool_calls=30,
            max_poll_time_minutes=15,
        ),
    )
except DeepResearchError as exc:
    # Handle or log deep research failures
    raise

xml_payload = compendium.to_xml_string()

# Alternate exports
markdown_doc = compendium.to_markdown()
html_files = compendium.to_html_site()  # Returns dict of filename -> content
pdf_bytes = compendium.to_pdf_bytes()
```

The returned `Compendium` object contains structured sections, insights, citations, and open questions.

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
</compendium>
```

This format is intentionally verbose to support downstream transformation. Markdown links within text (e.g., `[Label](URL)`) are preserved in the XML to ensure they render correctly in final outputs.

---

## Testing & Quality

- `pdm run pytest` — Executes the unit suite. Tests stub the OpenAI client, so they run offline.
- `pdm run flake8 src tests` — Linting.
- `pdm build` — Produce distributable artifacts.

If `pdm` fails to write log files in restricted environments, set `PDM_HOME` to a writable directory (for example, `export PDM_HOME=.pdm_home`).

---

## Contributing

1. Fork and clone the repository.
2. Run `pdm install --group dev`.
3. Make changes following the style guide and update/add tests.
4. Run `pdm run pytest` and `pdm run flake8 src tests`.
5. Raise a pull request with:
   - A concise description of the change.
   - Verification commands executed locally.
   - Representative XML samples if the user-facing structure changes.

---

## License

MIT © B.T. Franklin and contributors.
