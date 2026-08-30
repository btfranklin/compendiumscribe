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
5. `VerifierAgent` checks claims and required coverage against the approved topic, objective, plan, agenda, and guiding questions without web search. Warnings and optional metadata omissions do not block publication by themselves. It classifies blocking issues as repair, research, or fatal.
6. `EvidenceRepairAgent` receives the approved scope and can remove, narrow, qualify, or move affected content to open questions. It cannot search, add sources, or change source metadata.
7. If new evidence is required, the host saves the issue set and stops before search. `compendium recover --allow-paid-follow-up` authorizes one `TargetedResearchAgent` call for that saved issue set.
8. The application rebuilds the ledger after repair. One final verifier either accepts the evidence or stops the run. It keeps accurate issue resolutions when the repair limit is exhausted. Only an accepted report permits synthesis.
9. `SynthesisAgent` produces the final `CompendiumPayload` without web search.
10. Before each root agent run, the materialization result validates the complete contract input and serializes it for the SDK runner.
11. One Contract4Agents OpenAI trace router receives Agents SDK spans. Each research run opens a separate trace session. Each SDK call has an explicit attempt identity. The session records response checks, provider outcomes, and token use. It keeps raw responses from SDK exceptions. An unsupported, unknown, or ambiguous hosted call stops the run. Session close removes its router mappings. It does not create a false completion event when an SDK trace has no end event.
12. The deterministic host owns retries, recovery, stage order and cardinality, the repair limits, paid-search approval, terminal business decisions, and ledger-backed citation IDs. Stable invocation IDs and ordered retry attempts remain durable in host state and trace evidence. Paid search agents receive two total attempts. No-search agents receive three total attempts. Contract violations remain immediately terminal.
13. Contract4Agents assesses controls and the declared `CompendiumResearch` run specification separately. Conditional controls evaluate `when` before `require` and retain `applicable`, `not_applicable`, or `unverified` applicability. Run-spec observations come from the host's accepted stage ledger and must link to trace events carrying semantic agent identity.
14. `prepare_compendium_payload()` hydrates final citation metadata from the ledger, including publication, revision, and access metadata.
15. `Compendium.from_payload()` converts the stable payload into the renderer-facing dataclasses.

The workflow atomically persists `<base>.research.json` after accepted artifacts, atomically replaces `<base>.research.trace.jsonl` as normalized trace evidence grows, and checkpoints matching exact-frontier closure evidence to `<base>.research.trace-closure.json` before provider execution, after retry evidence, after accepted stages and terminal selection, and when the logical session closes. It records usage in `<base>.costs.json` when SDK usage metadata is available. A successful attempt is terminally selected only after its accepted stage record is durable; recovery reconciles the narrow state-before-selection crash window and writes a fresh frontier checkpoint. Progressed state requires matching trace and closure evidence during recovery, and completed recovery reruns both control and run-spec assurance before rendering.

Observed positive trace claims may be established directly. Absence, upper-bound, and missing-target claims remain unverified unless the closure manifest proves the relevant attempt, provider-response, and coverage-channel instrumentation was complete. The adapter claims only channels whose instrumentation path it can close; Compendium Scribe never upgrades event-family occurrence into proof of complete instrumentation.

## Compendium Library

`compendium create TOPIC --library PATH` keeps the normal output behavior and
also publishes the final `Compendium` into a strict filesystem-backed OKF
Library. The Library root and `compendiums/` directory have progressive
`index.md` files; compendium bundles live under `compendiums/<slug>/`.

Each compendium subtree contains `compendium.md`, typed section concepts,
typed source concepts, and frontmatter-free indexes. It is the canonical
Library content: XML, JSON cards/catalogs, display formats, symlinks, arbitrary
non-Markdown files, and `log.md` are rejected.

The CompendiumScribe profile is versioned independently from OKF. Its root
concept declares `profile: compendiumscribe` and `profile_version: "1"`.
Generated concepts use deterministic frontmatter, relative links, and
reversible Markdown bodies so `Compendium.from_okf_bundle()` reconstructs the
renderer-facing dataclasses.

`compendium library import LIBRARY_PATH SOURCE_PATH` accepts either a validated
CompendiumScribe OKF directory or an XML file. XML is parsed transiently and
written as OKF; it is never copied into the Library. Publishing and importing
use `slugify(compendium.topic)` for stable ids. Re-publishing the same title
replaces its complete subtree, while a different title collision receives a
numeric suffix such as `-2`.

## Key Boundaries

- `agent_contracts/types/` is the canonical schema boundary. Generated Pydantic models live under `agent_contracts/generated/python/` and are never hand-edited.
- Contract generation selects only the `python` target that this package uses.
- `research/agents_workflow/artifacts.py` owns only host workflow state and application-specific citation preparation.
- `agent_contracts/` owns portable instructions, capability grants, quality rubrics, controls, and run-stage declarations; `contract4agents.targets.toml` owns complete named model/provider profiles plus OpenAI adapter and tool bindings.
- `research/agents_workflow/agents.py` selects a complete committed Contract4Agents profile and materializes the OpenAI Agents SDK graph; environment variables select the profile but do not reconstruct model or provider configuration.
- Runtime code keeps the complete materialization result as the authority for native agents, the plan, strict root inputs, and the exact compiler artifacts. It compares the generated package contract digest with the materialized artifact digest before use. The small pre-materialization cost lookup reads the selected binding directly. Observed `provider_model` values remain trace telemetry. They do not have to equal planned model strings because provider aliases, snapshots, and routing can differ.
- `research/agents_workflow/contract_trace.py` owns the OpenAI trace router, run sessions, attempt scopes, and atomic trace writes. Contract4Agents owns provider-event classification, closure merge, grant resolution, trace checks, and assurance algorithms.
- Compendium Scribe assesses required controls and the selected run specification before rendering, but does not emit a Contract4Agents assurance bundle. Bundle creation remains deferred until a release-review, incident, compliance, or other concrete consumer needs that portable artifact.
- `research/agents_workflow/runner.py` is the SDK adapter boundary. Tests should stub `AgentRunner` instead of making live API calls.
- `research/agents_workflow/source_ledger.py` owns URL normalization, deduplication, section usage, and citation IDs.
- `published_at` stores the source publication date. `revision` stores a commit SHA, tag, or document version. `accessed_at` stores the timezone-aware access time.
- Missing optional provenance does not block publication by itself. A missing revision can block only a claim that depends on the exact state of a mutable source. Approved targeted research can update provenance for an existing source URL.
- `compendium/payload_parser.py` owns the public payload-to-model conversion. Keep this compatible with renderers unless intentionally changing the output contract.
- `compendium/okf.py` owns the strict profile, deterministic rendering/parsing, validation, and staged standalone bundle writes.
- `library/storage.py` owns nested OKF Library initialization, discovery, validation, import, subtree replacement, and index generation.
- `research/data/pricing.standard.json` is a local pricing catalog, not a live pricing source. Update it only from official OpenAI pricing sources and adjust pricing tests with the change.

## Dependency Direction

- CLI may import public research, compendium, and library APIs.
- `research/agents_workflow/` may import `compendium` only at the final construction point.
- `compendium/` must not import research workflow modules.
- Agent instructions live in `src/compendiumscribe/agent_contracts/agents/`; regenerate committed language bindings whenever canonical types change.

## Current Research Path

There is one runnable research path: the bounded Agents SDK workflow described above. Keep new orchestration work aligned with the runner adapter, state sidecar, source ledger, and committed named profiles.
