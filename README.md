# Compendium Scribe

![Compendium Scribe banner](https://raw.githubusercontent.com/btfranklin/compendiumscribe/main/.github/social%20preview/compendiumscribe_social_preview.jpg "Compendium Scribe")

[![Build Status](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml/badge.svg)](https://github.com/btfranklin/compendiumscribe/actions/workflows/python-package.yml) [![Supports Python versions 3.12+](https://img.shields.io/pypi/pyversions/compendiumscribe.svg)](https://pypi.python.org/pypi/compendiumscribe)

Compendium Scribe is a Click-driven command line tool and library that builds sourced research compendiums through a bounded OpenAI Agents SDK workflow. It decomposes a topic into planning, web research, verification, and synthesis stages, then renders the final `Compendium` as a strict Open Knowledge Format (OKF) bundle, XML, HTML, or PDF.

---

## Features

- **Agents SDK research workflow** - Runs planner, research manager, section researcher, verifier, and synthesis agents with structured Pydantic outputs.
- **Packaged agent definitions** - Materializes the complete Agents SDK graph from agent instructions, capability grants, output types, and runtime configuration.
- **Generated portable models** - Generates the Pydantic models used by the application from the canonical contract types.
- **Hosted web search where it belongs** - Enables web search for research manager, section research, and verification agents; planner and synthesis stay source-controlled.
- **Stable renderer contract** - Final agent output is validated and passed through the existing `Compendium.from_payload()` shape.
- **Citation ledger** - Deduplicates URLs, assigns citation IDs, tracks section usage, and rejects final citations that are not ledger-backed.
- **Research trace evidence** - Records attempts, provider outcomes, token use, and exact trace checkpoints. It checks controls and workflow stages before rendering.
- **Fail-closed capability evidence** - Rejects unsupported or unknown provider-hosted response calls and calls outside an agent's declared grants.
- **Recoverable sidecars** - Writes research state, trace events, trace-closure evidence, usage, and cost data to separate local files.
- **Local cost estimates** - Uses a checked-in pricing catalog for GPT-5.6 Sol, GPT-5.5, and GPT-5.4 family token rates, long-context uplifts where applicable, and built-in tool call pricing when usage metadata is available.
- **Strict OKF output** - Writes typed, linked Markdown concepts with safe YAML frontmatter and deterministic validation.
- **Compendium Library publishing** - Publishes self-contained OKF compendium trees into a movable, progressively disclosed OKF library.
- **Re-rendering** - Ingests existing OKF or XML compendiums to generate display or interchange formats without re-running research.
- **Offline tests** - The workflow uses a runner adapter so tests can stub Agents SDK runs without live API calls.

---

## Quick Start

### 1. Install

```bash
pdm install --dev
```

Ensure `PDM_HOME` points to a writable location when developing within a sandboxed environment.

### 2. Configure credentials

Copy the example environment file, then add your OpenAI credentials:

```bash
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. The example selects the bundled production runtime profile and sets the maximum agent turns; both values may be adjusted for a deployment. Missing or unknown profile configuration is rejected before cost initialization or research begins.

The research workflow uses the OpenAI Agents SDK with hosted web search enabled on the manager, section, and verifier agents.

Cost reports use the local catalog in `src/compendiumscribe/research/data/pricing.standard.json`. The catalog currently covers GPT-5.6 Sol, GPT-5.5, and GPT-5.4 family token pricing, long-context rates where applicable, web search calls, and Responses API file search calls. If a model is missing from the catalog, token usage is still recorded and USD estimates are left unavailable.

### 3. Generate a compendium

```bash
pdm run compendium create "Lithium-ion battery recycling"
```

Options:

- `--output PATH` - Base path/filename for the output. The extension is ignored.
- `--format FORMAT` - Output format, defaulting to `okf`. Available: `okf`, `xml`, `html`, `pdf`. Repeat for multiple outputs.
- `--library PATH` - Also publish the finished compendium into a Compendium Library directory.

If you pass `--output report`, Compendium Scribe writes:

- `report.okf/` by default, or the requested render formats
- `report.research.json`
- `report.research.trace.jsonl`
- `report.research.trace-closure.json`
- `report.costs.json`

Without `--output`, the base name is the slugified topic plus a UTC timestamp.

### 4. Publish to a Compendium Library

A Compendium Library is itself a strict OKF bundle that agents can scan
progressively. Its indexes link to self-contained compendium subtrees:

```text
research-library/
├── index.md
└── compendiums/
    ├── index.md
    └── lithium-ion-battery-recycling/
        ├── index.md
        ├── compendium.md
        ├── sections/
        │   ├── index.md
        │   └── s01.md
        └── sources/
            ├── index.md
            └── c01.md
```

Creation works the same as usual unless `--library` is provided. When it is
provided, requested outputs are still written normally, and the final compendium
is also upserted into the library:

```bash
pdm run compendium create "Lithium-ion battery recycling" \
  --output report \
  --format okf \
  --format xml \
  --library research-library
```

Import an existing XML compendium:

```bash
pdm run compendium library import research-library report.xml
```

Import an existing CompendiumScribe OKF bundle the same way:

```bash
pdm run compendium library import research-library report.okf
```

Validate a Library:

```bash
pdm run compendium library validate research-library
```

Library entries are idempotent by slugified title. Re-publishing the same title
replaces its complete OKF subtree. If another title would use the same slug, the
new entry gets a numeric suffix such as `-2`.

### 5. Recover a research run

Recovery resumes from the next incomplete stage in the sidecar state file:

```bash
pdm run compendium recover --input report.research.json
```

The recover command writes outputs using the same base path as the sidecar. For example, `report.research.json` renders to `report.okf/` when the stored format is OKF. Recovery states that request the removed `md` format are rejected rather than silently reinterpreted.
Recovery appends to the matching normalized trace only when its workflow and runtime-configuration digests still match and its closure manifest attests the trace's exact ordered frontier. Any sidecar containing accepted workflow progress or attempted agent work requires a readable, nonempty trace and matching identity-bound trace-closure evidence; only a pristine `created` sidecar may start without them. Logical invocation IDs remain stable across recovery, while each retry receives a unique, ordered attempt ID linked to its predecessor. A prior attempt is sealed across processes; resumed provider execution always uses the next attempt identity. SDK exceptions and invalid canonical outputs receive at most five total attempts; the fifth failure is terminal and later recovery will not spend another call. Undeclared capabilities fail immediately without retry. Successful attempts are selected only after their host stage records are checkpointed. Every completed recovery rechecks its required controls and workflow stages before citation hydration or rendering.

Progressed sidecars created by Compendium Scribe `v0.7.0` or earlier use incompatible evidence formats and cannot be resumed safely by newer builds. Restart those research runs from the original topic instead of copying, rewriting, or fabricating closure evidence.

### 6. Render formats from existing OKF or XML

```bash
pdm run compendium render my-topic.okf --format html
```

Options:

- `--format FORMAT` - Output format(s) to generate: `okf`, `xml`, `html`, `pdf`.
- `--output PATH` - Base path/filename for the output.

Directory outputs remain separate: `--output report --format okf` writes
`report.okf/`, while `--format html` writes `report/`.

---

## Python API Usage

```python
from compendiumscribe import build_compendium, ResearchConfig, DeepResearchError

try:
    compendium = build_compendium(
        "Emerging pathogen surveillance",
        config=ResearchConfig(),
    )
except DeepResearchError:
    raise

xml_payload = compendium.to_xml_string()
okf_files = compendium.to_okf_bundle()
html_files = compendium.to_html_site()
pdf_bytes = compendium.to_pdf_bytes()
```

Load a canonical OKF bundle with
`Compendium.from_okf_bundle("report.okf")`. XML remains available for
interchange, but it does not carry arbitrary OKF extension metadata.

---

## CompendiumScribe OKF Profile

OKF remains Markdown, but the removed `md` format was a single untyped
rendering. The canonical OKF representation is a directory of typed concepts:

```text
report.okf/
├── index.md
├── compendium.md
├── sections/
│   ├── index.md
│   └── s01.md
└── sources/
    ├── index.md
    └── c01.md
```

Every non-index document contains safe YAML frontmatter with a non-empty
`type`. The root concept declares `profile: compendiumscribe` and
`profile_version: "1"`. Section tags come from key terms; compendium tags are
derived deterministically. Relative links connect insights to source concepts,
so the same subtree works as a standalone export or inside a Library.

The profile rejects `log.md`, symlinks, non-Markdown files, path traversal,
colliding normalized IDs, malformed frontmatter, and broken required links.
Unknown producer-defined frontmatter keys remain valid.

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
