# Quality And Validation

## Required Local Loop

Run these before calling implementation work complete:

```bash
pdm run check
```

`pdm run check` runs the full required loop:

```bash
pdm run pytest
pdm run ruff check src tests
pdm build
```

`pdm run pytest` is expected to run offline. Research workflow tests should use the `AgentRunner` adapter and stub outputs instead of live OpenAI calls.

## Test Ownership

- CLI behavior: `tests/test_cli.py`
- OpenAI client setup: `tests/test_create_llm_clients.py`
- Compendium model and renderers: `tests/compendium/`
- Compendium Library persistence and import: `tests/library/`
- Research artifacts, ledger, workflow, pricing, and costs: `tests/research/`
- Repo legibility and forward-facing documentation checks: `tests/test_repo_legibility.py`

## High-Value Invariants

- Final synthesis may only cite IDs that exist as `cited` entries in `SourceLedger`, and final citation metadata must be hydrated from the ledger.
- Recovery resumes from `<base>.research.json`; it must not depend on a background response ID.
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

The legibility test checks that entry-point docs route agents to the current system of record and show the required research model settings.
