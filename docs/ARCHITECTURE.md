# Architecture

Compendium Scribe has three main surfaces:

- CLI orchestration in `src/compendiumscribe/cli.py`
- research workflow and telemetry in `src/compendiumscribe/research/`
- renderer-facing compendium model in `src/compendiumscribe/compendium/`
- filesystem library publishing in `src/compendiumscribe/library/`

## Runtime Flow

`compendium create TOPIC` constructs a `ResearchConfig`, validates that all required agent model settings are present, initializes the local cost report, and calls `build_compendium()`. The public function delegates to `research/agents_workflow/orchestrator.py`, which owns the bounded Agents SDK workflow:

1. `PlannerAgent` creates a `ResearchPlan` without web search.
2. `ResearchManagerAgent` uses hosted web search to produce a `ResearchAgenda`.
3. `SectionResearchAgent` runs sequentially once per agenda section.
4. The application builds a `SourceLedger` from section sources and finding URLs.
5. `VerifierAgent` checks source coverage and may request one targeted follow-up pass.
6. `SynthesisAgent` produces the final `CompendiumPayload` without web search.
7. `prepare_compendium_payload()` rejects any final citation reference that is not backed by a cited ledger entry, then hydrates final citation metadata from the ledger.
8. `Compendium.from_payload()` converts the stable payload into the renderer-facing dataclasses.

The workflow persists `<base>.research.json` after accepted artifacts and records usage in `<base>.costs.json` when SDK usage metadata is available.

## Compendium Library

`compendium create TOPIC --library PATH` keeps the normal output behavior and
also publishes the final `Compendium` into a filesystem-backed library. The
library root is identified by `catalog.json`; compendium bodies live under
`compendiums/<slug>/`.

Each library entry stores:

- `compendium.xml` as canonical structured content.
- `compendium.md` as an agent-readable convenience rendering.
- `card.json` as medium-depth progressive-disclosure metadata.

`catalog.json` stays compact: it includes schema version, update time, and one
entry per compendium with title, summary, keywords, and relative paths to the
XML, Markdown, and card files. Libraries are movable because JSON paths are
relative to the library root.

`compendium library import LIBRARY_PATH COMPENDIUM_XML` parses XML through
`Compendium.from_xml_file()`, writes normalized XML and Markdown, builds the
card, and upserts the catalog entry. Publishing and importing use
`slugify(compendium.topic)` for stable ids. If a different title collides with
an existing slug, the storage layer appends numeric suffixes such as `-2`.

## Key Boundaries

- `research/agents_workflow/artifacts.py` is the schema boundary for agent outputs and state files.
- `research/agents_workflow/runner.py` is the SDK adapter boundary. Tests should stub `AgentRunner` instead of making live API calls.
- `research/agents_workflow/source_ledger.py` owns URL normalization, deduplication, section usage, and citation IDs.
- `compendium/payload_parser.py` owns the public payload-to-model conversion. Keep this compatible with renderers unless intentionally changing the output contract.
- `library/storage.py` owns library initialization, catalog upserts, import, relative paths, cards, and deterministic JSON writes.
- `research/data/pricing.standard.json` is a local pricing catalog, not a live pricing source. Update it only from official OpenAI pricing sources and adjust pricing tests with the change.

## Dependency Direction

- CLI may import public research, compendium, and library APIs.
- `research/agents_workflow/` may import `compendium` only at the final construction point.
- `compendium/` must not import research workflow modules.
- Prompt files under `src/compendiumscribe/prompts/` are loaded by agent definitions; keep prompt filenames aligned with their loader.

## Current Research Path

There is one runnable research path: the bounded Agents SDK workflow described above. Keep new orchestration work aligned with the runner adapter, state sidecar, source ledger, and explicit per-agent model settings.
