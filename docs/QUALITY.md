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

`pdm run contracts:check` validates the packaged contract project and fails when generated Pydantic models are stale. `pdm run pytest` is expected to run offline. Research workflow tests should use the `AgentRunner` adapter and stub outputs instead of live OpenAI calls.

The reusable `Python package` workflow runs this aggregate check and strict
Twine archive checks on Python 3.12, 3.13, and 3.14 for ordinary CI and before
creating a tag-triggered draft release. Release publication only rebuilds and
publishes the package from that tag; see [Releasing](RELEASING.md).

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
- Only an `accepted` verification report may reach synthesis. Verification stays within the approved topic, objective, plan, agenda, and guiding questions. Warnings use the `none` resolution and do not block publication. Repair and research issues must name a known section. Fatal issues stop the run.
- The no-search repair may change only affected summaries, findings, and open questions. It must preserve section identity, guiding questions, and source records. It cannot cite a URL that was not in the affected brief.
- Targeted web research requires the explicit `--allow-paid-follow-up` recovery flag. Approval is not saved. The host runs no more than one targeted-research call and one final verifier.
- The source ledger is rebuilt and validated after each repair stage. A final verification that identifies more work cannot start another repair or research cycle. Its issue resolutions remain accurate and are not changed to fatal only because the repair limit is exhausted.
- Every observed provider-hosted response call must be supported and resolve to exactly one enabled materialization-plan grant; unsupported, unknown, ambiguous, and contradictory evidence is persisted and fails the run. Host-dispatched calls remain outside this adapter classification.
- One OpenAI trace router is registered per process, while every logical research run uses a disposable session. Session close must release every owned router mapping even when the SDK omits its trace-end callback, while leaving that lifecycle incomplete. Every SDK invocation runs inside an explicit trace attempt. Invocation IDs stay stable across recovery; attempt IDs are unique and ordered, retries identify their predecessor, and exception-carried raw responses remain evidence. Paid search agents receive two total attempts. No-search agents receive three total attempts.
- A successful SDK result must record response, provider-outcome, and usage evidence. An SDK exception must record all available response, outcome, and usage evidence. A zero-response path must leave a batch receipt. Each checkpoint must match the exact trace event count and prefix digest. Retryable failures receive two total attempts for paid search agents and three total attempts for no-search agents.
- Canonical output validation failures remain attempt evidence. Only a valid attempt may be terminally selected as successful, and selection occurs after its host stage checkpoint is durable. The last configured retryable failure is selected as terminally failed; undeclared capabilities are terminal on first observation.
- Conditional controls evaluate `when` before `require`; applicability is `applicable`, `not_applicable`, or `unverified`. Required Contract4Agents controls and the `CompendiumResearch` run-spec result must be `passed`; `violated` and `unverified` both fail the run.
- Positive observed trace claims may pass from direct evidence. Negative, absence, upper-bound, and missing-target claims require matching closure for the relevant coverage channel and remain unverified without it.
- Run-spec observations come from the host's authoritative stage ledger and link to semantic trace events. Missing agent identity is unverified, never a pass.
- Persisted enum-valued contract artifacts must pass generated-model validation before recovery resumes.
- Generated contract files must be current. Their package digest must match the
  exact compiler artifacts from materialization. Root agent inputs must pass the
  materialized strict input contract before the SDK runner starts.
- Progressed recovery requires a readable, nonempty trace and identity-bound closure manifest with matching contract and materialization-plan digests plus an exact ordered trace frontier. A prior attempt is sealed across sessions; a resumed provider call must use the next attempt identity and preserve its `retry_of` parent. Completed recovery must reassess the merged evidence before rendering.
- Recovery resumes from `<base>.research.json`, extends normalized events in `<base>.research.trace.jsonl`, and updates closure evidence in `<base>.research.trace-closure.json`; it must not depend on a background response ID.
- Research state, normalized trace, and trace-closure sidecars must be atomically replaced so failed writes preserve the previous complete file.
- Assurance bundles are not emitted without a concrete downstream consumer; this does not weaken the mandatory in-process control and run-spec assessments.
- Pricing estimates are best-effort. Missing pricing must not fail a research run.
- The pricing catalog records a full `last_updated_utc` timestamp. Its first use in a process warns when the timestamp is missing, invalid, or more than 90 elapsed days old. The warning does not stop research.
- Source publication dates, revisions, and access times remain separate through payload, OKF, XML, HTML, and PDF output. `accessed_at` must be a timezone-aware ISO 8601 timestamp. Missing optional provenance does not block publication by itself. Approved targeted research can update provenance for an existing source URL.
- Omitted `--library` must preserve requested standalone outputs; specified libraries must write only a validated nested OKF compendium subtree and deterministic indexes.
- Standalone OKF writes and Library replacement candidates must validate before replacing existing content.
- Compendium and Library links must be relative so subtrees and whole Libraries remain movable.
- `log.md`, symlinks, non-Markdown files, malformed frontmatter, colliding normalized IDs, path traversal, and broken required links must fail closed.
- Recovery state requesting the removed `md` format must fail explicitly instead of being aliased to OKF.
- Tests must not require `OPENAI_API_KEY` for normal offline validation.

## Documentation Freshness

When behavior shifts, update these in the same change:

- `README.md` for user-facing commands and configuration.
- `AGENTS.md` for navigation and required checks.
- `docs/ARCHITECTURE.md` for workflow or boundary changes.
- `.env.example` for environment variable changes.

The legibility tests resolve local links from the agent and documentation entry points, derive the required Contract4Agents profile selector from `ResearchConfig`, and verify that the parsed README environment example matches `.env.example`.
