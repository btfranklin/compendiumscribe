# Architecture

Compendium Scribe has four main surfaces:

- CLI orchestration in `src/compendiumscribe/cli.py`
- research workflow and telemetry in `src/compendiumscribe/research/`
- renderer-facing compendium model in `src/compendiumscribe/compendium/`
- filesystem library publishing in `src/compendiumscribe/library/`

## Runtime Flow

`compendium create TOPIC` constructs a `ResearchConfig`, validates the required named-profile selection, initializes the local cost report from that profile's committed model, and calls `build_compendium()`. The public function delegates to `research/agents_workflow/orchestrator.py`, which owns the bounded Agents SDK workflow. Agents and their runtime instructions are built from the packaged Contract4Agents project under `src/compendiumscribe/agent_contracts/`:

1. `PlannerAgent` creates a `ResearchPlan` without web search.
2. `ResearchManagerAgent` uses hosted web search to produce a `ResearchAgenda`.
3. `SectionResearchAgent` runs sequentially once per agenda section.
4. The application builds a `SourceLedger` from section sources and finding URLs.
5. `VerifierAgent` checks source coverage and may request one targeted follow-up pass. Only an `accepted` terminal report permits synthesis.
6. `SynthesisAgent` produces the final `CompendiumPayload` without web search.
7. One process-wide Contract4Agents OpenAI trace router receives Agents SDK spans. Each logical research run opens a disposable trace session, and every SDK invocation executes inside an explicit attempt scope. The session records successful response or batch normalization receipts, including zero-response paths, and preserves raw responses retained on SDK exceptions; unsupported, unknown, or ambiguously granted provider-hosted calls fail closed. Session close detaches every router mapping it owns without fabricating completion for a missing SDK trace end.
8. The deterministic host owns retries, recovery, stage order and cardinality, the one-follow-up limit, terminal business decisions, and ledger-backed citation IDs. Stable invocation IDs and ordered retry attempts remain durable in host state and trace evidence. SDK exceptions and schema-invalid outputs receive five total attempts across the initial run and recovery; the fifth failure is terminal. Contract violations remain immediately terminal.
9. Contract4Agents assesses controls and the declared `CompendiumResearch` run specification separately. Conditional controls evaluate `when` before `require` and retain `applicable`, `not_applicable`, or `unverified` applicability. Run-spec observations come from the host's accepted stage ledger and must link to trace events carrying semantic agent identity.
10. `prepare_compendium_payload()` hydrates final citation metadata from the ledger.
11. `Compendium.from_payload()` converts the stable payload into the renderer-facing dataclasses.

The workflow atomically persists `<base>.research.json` after accepted artifacts, atomically replaces `<base>.research.trace.jsonl` as normalized trace evidence grows, and checkpoints matching exact-frontier closure evidence to `<base>.research.trace-closure.json` before provider execution, after retry evidence, after accepted stages and terminal selection, and when the logical session closes. It records usage in `<base>.costs.json` when SDK usage metadata is available. A successful attempt is terminally selected only after its accepted stage record is durable; recovery reconciles the narrow state-before-selection crash window and writes a fresh frontier checkpoint. Progressed state requires matching trace and closure evidence during recovery, and completed recovery reruns both control and run-spec assurance before rendering.

Observed positive trace claims may be established directly. Absence, upper-bound, and missing-target claims remain unverified unless the closure manifest proves the relevant attempt, provider-response, and coverage-channel instrumentation was complete. The adapter claims only channels whose instrumentation path it can close; Compendium Scribe never upgrades event-family occurrence into proof of complete instrumentation.

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

- `agent_contracts/types/` is the canonical schema boundary. Generated Pydantic, TypeScript, and Zod bindings live under `agent_contracts/generated/` and are never hand-edited.
- Contract generation explicitly selects the `python` and `typescript` targets. Contract4Agents 0.12.2 freezes its owned serialized format fields at `"1"` throughout the 0.x product line, so the package minimum—not the format integer—is the compatibility signal.
- `research/agents_workflow/artifacts.py` owns only host workflow state and application-specific citation preparation.
- `agent_contracts/` owns portable instructions, capability grants, quality rubrics, controls, and run-stage declarations; `contract4agents.targets.toml` owns complete named model/provider profiles plus OpenAI adapter and tool bindings.
- `research/agents_workflow/agents.py` selects a complete committed Contract4Agents profile and materializes the OpenAI Agents SDK graph; environment variables select the profile but do not reconstruct model or provider configuration.
- Runtime code consumes the IR and plan returned by that one materialization. The small pre-materialization cost lookup reads the selected binding directly. Observed `provider_model` values remain trace telemetry; they are not required to equal planned model strings because provider aliases, snapshots, and routing may differ.
- `research/agents_workflow/contract_trace.py` owns the one process-wide OpenAI trace router, disposable logical-run sessions, attempt scopes, and atomic persistence of normalized trace plus exact-frontier capture snapshots; provider-event classification, cross-session closure merge, grant resolution, trace conformance, and assurance algorithms stay upstream.
- Compendium Scribe assesses required controls and the selected run specification before rendering, but does not emit a Contract4Agents assurance bundle. Bundle creation remains deferred until a release-review, incident, compliance, or other concrete consumer needs that portable artifact.
- `research/agents_workflow/runner.py` is the SDK adapter boundary. Tests should stub `AgentRunner` instead of making live API calls.
- `research/agents_workflow/source_ledger.py` owns URL normalization, deduplication, section usage, and citation IDs.
- `compendium/payload_parser.py` owns the public payload-to-model conversion. Keep this compatible with renderers unless intentionally changing the output contract.
- `library/storage.py` owns library initialization, catalog upserts, import, relative paths, cards, and deterministic JSON writes.
- `research/data/pricing.standard.json` is a local pricing catalog, not a live pricing source. Update it only from official OpenAI pricing sources and adjust pricing tests with the change.

## Dependency Direction

- CLI may import public research, compendium, and library APIs.
- `research/agents_workflow/` may import `compendium` only at the final construction point.
- `compendium/` must not import research workflow modules.
- Agent instructions live in `src/compendiumscribe/agent_contracts/agents/`; regenerate committed language bindings whenever canonical types change.

## Current Research Path

There is one runnable research path: the bounded Agents SDK workflow described above. Keep new orchestration work aligned with the runner adapter, state sidecar, source ledger, and committed named profiles.

Progressed `v0.6.x` research sidecars have no identity-bound closure manifest and must be restarted. Progressed `v0.7.0` sidecars use the pre-freeze Contract4Agents 0.12.1 formats, while unreleased 0.11 sidecars use an earlier incompatible evidence shape. Contract4Agents 0.12.2 intentionally rejects both; restart the run rather than inferring, migrating, or rewriting its evidence.
