# Agent Map

This repo is a Python package for generating sourced compendiums through a bounded OpenAI Agents SDK workflow. Keep this file short; deeper context lives in [README.md](README.md) and the [documentation index](docs/README.md).

## Start Here

- Product and CLI usage: [README.md](README.md)
- Architecture, quality, and release guidance: [documentation index](docs/README.md)
- Research workflow code: [agents_workflow](src/compendiumscribe/research/agents_workflow/)
- Packaged agent contracts: [agent_contracts](src/compendiumscribe/agent_contracts/)
- Renderer-facing model: [compendium](src/compendiumscribe/compendium/)
- Compendium Library persistence: [library](src/compendiumscribe/library/)

## Common Tasks

- Change CLI behavior in [cli.py](src/compendiumscribe/cli.py); mirror user-visible changes in [README.md](README.md) and CLI tests.
- Change research orchestration in [agents_workflow](src/compendiumscribe/research/agents_workflow/); keep tests offline by using the runner adapter, and keep the packaged Contract4Agents project aligned.
- Change agent contracts and instructions in [agent_contracts](src/compendiumscribe/agent_contracts/); run strict drift and update contract tests.
- Change final output shape in [compendium](src/compendiumscribe/compendium/); update payload, XML, Markdown, HTML, and parser tests together.
- Change library publishing/import in [library](src/compendiumscribe/library/); keep `catalog.json`, `card.json`, and CLI tests aligned.
- Change pricing in [pricing.standard.json](src/compendiumscribe/research/data/pricing.standard.json); update [test_pricing.py](tests/research/test_pricing.py) and cost tests.

## Required Checks

Before calling work complete:

```bash
pdm run check
```

`pdm run check` runs the required validation loop:

```bash
pdm run contracts:check
pdm run pytest
pdm run ruff check src tests
pdm build
```

Use PDM for dependency management. Keep dependency constraints as `>=` minimums, and when adding packages set the minimum to the latest available version at implementation time.
