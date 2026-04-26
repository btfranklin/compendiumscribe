# Architecture

Compendium Scribe has three main surfaces:

- CLI orchestration in `src/compendiumscribe/cli.py`
- research workflow and telemetry in `src/compendiumscribe/research/`
- renderer-facing compendium model in `src/compendiumscribe/compendium/`

## Runtime Flow

`compendium create TOPIC` constructs a `ResearchConfig`, initializes the local cost report, and calls `build_compendium()`. The public function delegates to `research/agents_workflow/orchestrator.py`, which owns the bounded Agents SDK workflow:

1. `PlannerAgent` creates a `ResearchPlan` without web search.
2. `ResearchManagerAgent` uses hosted web search to produce a `ResearchAgenda`.
3. `SectionResearchAgent` runs sequentially once per agenda section.
4. The application builds a `SourceLedger` from section sources and finding URLs.
5. `VerifierAgent` checks source coverage and may request one targeted follow-up pass.
6. `SynthesisAgent` produces the final `CompendiumPayload` without web search.
7. `validate_compendium_citations()` rejects any final citation that is not backed by a cited ledger entry.
8. `Compendium.from_payload()` converts the stable payload into the renderer-facing dataclasses.

The workflow persists `<base>.research.json` after accepted artifacts and records usage in `<base>.costs.json` when SDK usage metadata is available.

## Key Boundaries

- `research/agents_workflow/artifacts.py` is the schema boundary for agent outputs and state files.
- `research/agents_workflow/runner.py` is the SDK adapter boundary. Tests should stub `AgentRunner` instead of making live API calls.
- `research/agents_workflow/source_ledger.py` owns URL normalization, deduplication, section usage, and citation IDs.
- `compendium/payload_parser.py` owns the public payload-to-model conversion. Keep this compatible with renderers unless intentionally changing the output contract.
- `skill_output.py` is separate from the research workflow. It can make LLM calls when rendering `--format skill`.
- `research/data/pricing.standard.json` is a local pricing catalog, not a live pricing source. Update it only from official OpenAI pricing sources and adjust pricing tests with the change.

## Dependency Direction

- CLI may import public research, compendium, and skill output APIs.
- `research/agents_workflow/` may import `compendium` only at the final construction point.
- `compendium/` must not import research workflow modules.
- Prompt files under `src/compendiumscribe/prompts/` are loaded by agent definitions or skill output code; keep prompt filenames aligned with their loader.

## Removed Legacy Path

There is no runnable single background research response path. Do not reintroduce legacy concepts such as `--no-background`, `--max-tool-calls`, `DEEP_RESEARCH_MODEL`, `PROMPT_REFINER_MODEL`, or `timed_out_research.json` unless the product intentionally changes direction again.
