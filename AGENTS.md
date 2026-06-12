# Agent Map

This repo is a Python package for generating sourced compendiums through a bounded OpenAI Agents SDK workflow. Keep this file short; deeper context lives in `README.md` and `docs/`.

## Start Here

- Product and CLI usage: `README.md`
- Architecture and dependency boundaries: `docs/ARCHITECTURE.md`
- Validation and quality checks: `docs/QUALITY.md`
- Release process and tag-first release notes flow: `docs/RELEASING.md`
- Research workflow code: `src/compendiumscribe/research/agents_workflow/`
- Renderer-facing model: `src/compendiumscribe/compendium/`
- Compendium Library persistence: `src/compendiumscribe/library/`

## Common Tasks

- Change CLI behavior in `src/compendiumscribe/cli.py`; mirror user-visible changes in `README.md` and CLI tests.
- Change research orchestration in `src/compendiumscribe/research/agents_workflow/`; keep tests offline by using the runner adapter.
- Change final output shape in `src/compendiumscribe/compendium/`; update payload, XML, Markdown, HTML, and parser tests together.
- Change library publishing/import in `src/compendiumscribe/library/`; keep `catalog.json`, `card.json`, and CLI tests aligned.
- Change prompts in `src/compendiumscribe/prompts/`; keep prompt names aligned with `agents_workflow/agents.py`.
- Change pricing in `src/compendiumscribe/research/data/pricing.standard.json`; update `tests/research/test_pricing.py` and cost tests.

## Required Checks

Before calling work complete:

```bash
pdm run check
```

`pdm run check` runs the required validation loop:

```bash
pdm run pytest
pdm run ruff check src tests
pdm build
```

Use PDM for dependency management. Keep dependency constraints as `>=` minimums, and when adding packages set the minimum to the latest available version at implementation time.
