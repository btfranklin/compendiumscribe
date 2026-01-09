# Repository Guidelines

## Project Structure & Module Organization
The installable package remains under `src/compendiumscribe`. `cli.py` now exposes a Click-based entry point that accepts a topic argument and optional runtime flags. `model.py` defines the compendium dataclasses (`Compendium`, `Section`, `Insight`, `Citation`) plus XML serialization helpers. Deep-research orchestration lives in `research_domain.py`, which coordinates prompt planning and the `o3-deep-research` call while parsing the JSON payloads. Prompt templates live alongside the code as Markdown files (for example, `topic_blueprint.md`, `deep_research_assignment.md`) to keep the workflow editable. Tests sit in `tests/` and mirror the public surface area; add new fixtures or stubs there when expanding coverage.

## Build, Test, and Development Commands
- `pdm install --dev` installs runtime and dev dependencies (ensure `PDM_HOME` points to a writable path if running in a sandbox).
- `pdm run create-compendium "Cell biology"` exercises the CLI; add `--output path.xml`, `--no-background`, or `--max-tool-calls N` as needed.
- `pdm run pytest` is mandatory before calling work complete. Tests already rely on stubs, so they are fast and offline-capable. If `pdm` cannot write logs, set `PDM_HOME=.pdm_home` and retry.
- `pdm run ruff check src tests` keeps style and linting consistent; do not treat work as finished until this passes cleanly.
- `pdm build` produces the wheel and sdist when preparing a release.

## Coding Style & Naming Conventions
Follow PEP 8 conventions with four-space indentation and `snake_case` modules. Public functions, dataclasses, and configuration objects should carry type annotations and, where behavior is non-obvious, concise docstrings. Maintain explicit imports. When adding CLI options, keep flags lower-case and hyphenated, and document Click options with helpful copy. Prompt filenames should remain numerically ordered to signal execution order.

## Testing Guidelines
Pytest drives validation, and every change should finish with a green `pdm run pytest` run. Extend coverage by constructing `Compendium` instances and asserting the XML emitted by `to_xml_string`. When touching the research pipeline, prefer stubbing the OpenAI client (see `tests/test_xml_conversion.py`) so tests remain deterministic and offline. Add regression tests alongside any prompt or serialization changes, and rerun `pdm run pytest` before raising a PR or marking a task done.

## Commit & Pull Request Guidelines
Use short, sentence-case commit subjects that describe the change (e.g., `Clarified CLI background option`). Keep commits focused and update documentation when behavior shifts. Pull requests should state intent, link issues, list local verification commands, and include sample XML snippets when user-facing output changes.

## Environment & Secrets
Credentials load via `python-dotenv`. Set `OPENAI_API_KEY` (and any future tool credentials) in a local `.env` that remains untracked. Deep research requires OpenAI access with web-search tooling enabled; document any additional environment flags you introduce in `README.md`. Scrub sensitive data from generated compendia before sharing.
