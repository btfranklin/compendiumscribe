# Quality And Validation

## Required Local Loop

Run these before calling implementation work complete:

```bash
pdm run check
```

`pdm run check` runs the full required loop:

```bash
pdm run contracts:check
pdm run pytest
pdm run ruff check src tests
pdm build
```

`pdm run contracts:check` validates the packaged contract project and fails when generated Pydantic, TypeScript, or Zod bindings are stale. `pdm run pytest` is expected to run offline. Research workflow tests should use the `AgentRunner` adapter and stub outputs instead of live OpenAI calls.

## Test Ownership

- CLI behavior: `tests/test_cli.py`
- OpenAI client setup: `tests/test_create_llm_clients.py`
- Compendium model and renderers: `tests/compendium/`
- Compendium Library persistence and import: `tests/library/`
- Research artifacts, ledger, workflow, pricing, and costs: `tests/research/`
- Contract4Agents canonical IR, codegen freshness, target planning, and native materialization: `tests/research/test_agent_contracts.py`
- Repo legibility and forward-facing documentation checks: `tests/test_repo_legibility.py`

## High-Value Invariants

- Final synthesis may only cite IDs that exist as `cited` entries in `SourceLedger`, and final citation metadata must be hydrated from the ledger.
- Only an `accepted` verification report may reach synthesis; follow-up is limited to one pass over explicit, known section IDs.
- Every observed provider tool call must resolve to exactly one enabled materialization-plan grant; contradictory evidence is persisted and fails the run.
- Required Contract4Agents controls must be `passed`; `violated` and `unverified` both fail the run.
- Persisted enum-valued contract artifacts must pass generated-model validation before recovery resumes.
- Progressed recovery requires a readable, nonempty trace with matching contract and materialization-plan digests, and completed recovery must reassess it before rendering.
- Recovery resumes from `<base>.research.json` and extends the normalized evidence in `<base>.research.trace.jsonl`; it must not depend on a background response ID.
- Research state and normalized trace sidecars must be atomically replaced so failed writes preserve the previous complete file.
- Pricing estimates are best-effort. Missing pricing must not fail a research run.
- Omitted `--library` must preserve the existing create output set; specified libraries must write `catalog.json`, canonical XML, Markdown, and `card.json`.
- Library JSON must use relative paths so a library directory can be moved.
- Tests must not require `OPENAI_API_KEY` for normal offline validation.

## Documentation Freshness

When behavior shifts, update these in the same change:

- `README.md` for user-facing commands and configuration.
- `AGENTS.md` for navigation and required checks.
- `docs/ARCHITECTURE.md` for workflow or boundary changes.
- `.env.example` for environment variable changes.

The legibility tests resolve local links from the agent and documentation entry points, derive the required Contract4Agents profile selector from `ResearchConfig`, and verify that the parsed README environment example matches `.env.example`.
