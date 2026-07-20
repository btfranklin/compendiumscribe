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
- Follow-up completion is checkpointed per section. Once every target has run, the exhausted follow-up state is persisted before the second verifier starts so recovery cannot repeat paid research work.
- Every observed provider-hosted response call must be supported and resolve to exactly one enabled materialization-plan grant; unsupported, unknown, ambiguous, and contradictory evidence is persisted and fails the run. Host-dispatched calls remain outside this adapter classification.
- One OpenAI trace router is registered per process, while every logical research run uses a disposable session. Session close must release every owned router mapping even when the SDK omits its trace-end callback, while leaving that lifecycle incomplete. Every SDK invocation runs inside an explicit trace attempt. Invocation IDs stay stable across recovery; attempt IDs are unique and ordered, retries identify their predecessor, and exception-carried raw responses remain evidence. Retryable exceptions and schema-invalid outputs receive no more than five total attempts.
- Successful response normalization, exception-response normalization, and zero-response paths must leave response or batch receipts. Non-closing checkpoints and session close must persist identity-bound attempt, provider-response, and instrumentation-channel evidence at the normalized trace's exact event-count and canonical prefix digest.
- Canonical output validation failures remain attempt evidence. Only a valid attempt may be terminally selected as successful, and selection occurs after its host stage checkpoint is durable. A fifth retryable failure is selected as terminally failed; undeclared capabilities are terminal on first observation.
- Conditional controls evaluate `when` before `require`; applicability is `applicable`, `not_applicable`, or `unverified`. Required Contract4Agents controls and the `CompendiumResearch` run-spec result must be `passed`; `violated` and `unverified` both fail the run.
- Positive observed trace claims may pass from direct evidence. Negative, absence, upper-bound, and missing-target claims require matching closure for the relevant coverage channel and remain unverified without it.
- Run-spec observations come from the host's authoritative stage ledger and link to semantic trace events. Missing agent identity is unverified, never a pass.
- Persisted enum-valued contract artifacts must pass generated-model validation before recovery resumes.
- Progressed recovery requires a readable, nonempty trace and identity-bound closure manifest with matching contract and materialization-plan digests plus an exact ordered trace frontier. A prior attempt is sealed across sessions; a resumed provider call must use the next attempt identity and preserve its `retry_of` parent. Completed recovery must reassess the merged evidence before rendering.
- Recovery resumes from `<base>.research.json`, extends normalized events in `<base>.research.trace.jsonl`, and updates closure evidence in `<base>.research.trace-closure.json`; it must not depend on a background response ID.
- Progressed `v0.6.x` sidecars must be restarted because event occurrence cannot be upgraded into identity-bound closure after the original run.
- Progressed `v0.7.0` sidecars and unreleased sidecars from the Contract4Agents 0.11 integration must also be restarted rather than migrated or shimmed. Contract4Agents 0.12.2 freezes every owned serialized format field at `"1"` for the remainder of its 0.x line, so its package version—not the repeated format integer—is the compatibility signal.
- Research state, normalized trace, and trace-closure sidecars must be atomically replaced so failed writes preserve the previous complete file.
- Assurance bundles are not emitted without a concrete downstream consumer; this does not weaken the mandatory in-process control and run-spec assessments.
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
