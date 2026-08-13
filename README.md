# Design Flow System

> A persistent, resumable, single-owner design-governance prototype where recommendations remain advisory and only explicitly locked owner answers create authority.

## Identity

| Field | Current value |
|---|---|
| Version | `0.2.0` |
| Maturity | `PERSISTENT SINGLE-OWNER PROTOTYPE` |
| Authority | Owner answers are authoritative; recommendations are advisory |
| Runtime | Python 3.12+, standard library only |
| Upstream architecture | `fargo161/periodic-semantic-grammar` |
| PSG baseline | `6d1efe5f486082b6372d0ccaeefb85e0c32b13c6` |

The README is an orientation surface derived from the implementation. It is not independent design authority.

## What v0.2 Proves

The system can carry one project through:

```text
intake → draft round → owner answers → preview → explicit lock
       → atomic checkpoint → close → strict reload → resume
       → qualified/unresolved decision → later supersession
       → concept revision → living document + context handoff
```

The semantic guarantees stabilized in v0.1.1 remain intact:

- recommendations and reasons are preserved separately from owner answers;
- synthesis uses the normalized owner value through an explicit rule mapping;
- qualified answers remain unresolved instead of being guessed away;
- supersession is explicit, guarded, acyclic, and history-preserving;
- persisted supersession is activated only when status, direct relationships, exact transitive ancestry, and TRACE form one coherent graph;
- committed project, round, question, recommendation, and owner-answer records are immutable snapshots;
- concepts sourced from superseded decisions leave settled current state until explicitly resolved;
- authoritative decisions and concepts require matching local TRACE provenance;
- `DesignFlowWorkspace` remains the canonical cross-module integrity boundary.

## Authority and Working-State Law

```text
ASSISTANT RECOMMENDATION != OWNER DECISION
DRAFT != AUTHORITY
SAVE GENERATION != SEMANTIC REVISION
GENERATED MARKDOWN != SOURCE OF TRUTH
```

A draft may be imported from the strict JSON draft schema, answered, edited, previewed, saved, resumed, or abandoned without creating semantic history. A complete round becomes authoritative only through explicit `LOCK`. Lock runs on an isolated candidate workspace; synthesis, supersession, concept work, validation, and durable promotion must all succeed before the active project changes.

Historical correction creates a new decision and an explicit supersession edge. It never rewrites a committed owner answer.

## Durable Project Layout

```text
my-project/
├── manifest.json                 authoritative entry point
├── rounds.json                   authoritative round/answer history
├── decisions.json                authoritative ledger and relationships
├── concepts.json                 authoritative current/affected/history registry
├── unresolved.json               authoritative compiled unresolved register
├── trace.json                    authoritative append-only provenance
├── sessions.json                 operational, non-semantic session metadata
├── working/draft.json            operational, non-authoritative draft
├── sources/index.json            evidence metadata, not design authority
├── cache/current_state.json      replaceable derived cache
├── generated/
│   ├── living_application.md     derived artifact
│   └── context_handoff.md        derived artifact
└── sources/                      optional project-local evidence copies
```

The manifest owns project identity, the `0.2.0` project-format version, application version, save generation, the complete registered-file set, SHA-256 hashes, artifact metadata, and the canonical JSON contract. The directory name is not project identity.

Authoritative and operational JSON is canonical UTF-8 with sorted keys, compact separators, and one final newline. Unknown fields are rejected. Python implementation objects are never serialized.

See [docs/PERSISTENCE.md](docs/PERSISTENCE.md) for the precise activation, hashing, recovery, and portability contracts.

## Save and Load Integrity

Every successful checkpoint increments `save_generation` without adding TRACE or fabricating semantic history. Save constructs and validates a complete sibling candidate directory, then promotes it. Existing state is first renamed to a unique sibling backup and restored if candidate promotion fails.

The storage commit point is the successful `candidate -> target` rename. Failure before that point leaves or restores prior authority. Backup deletion occurs after the commit point; cleanup failure returns a truthful recovery warning while the new canonical target remains committed. The leftover backup blocks future ordinary activation until owner review.

This is a best portable directory-swap approximation, not a claim of one indivisible multi-directory filesystem transaction. A process or machine interruption can leave a candidate or backup sibling. Load detects those recovery artifacts and refuses activation pending owner review; it never guesses which directory to trust.

Load is a staged semantic activation gate. It verifies:

1. manifest schema and supported format;
2. exact file registry and consistent save generation;
3. canonical bytes and SHA-256 for every registered file;
4. envelope role/project/generation agreement;
5. strict record schemas and immutable reconstruction;
6. TRACE IDs and provenance;
7. round, answer, decision, supersession, unresolved, concept, and cross-reference integrity;
8. current-state compilation.

Corruption, missing files, hash changes, unknown fields, mixed generations, unsupported formats, forged TRACE, and invalid references block activation. Generated Markdown is never used to repair authority.

## Sessions, Sources, and Artifacts

A project is durable authority. A session is only a bounded operating episode over that project. Session metadata records its ID, project ID, timestamps, rounds touched/committed, save generations, and generated artifacts. Activation validates round references, the touched/committed relationship, generation bounds, and the single-open-session model; resume reuses that open session. Raw chat is not continuity authority.

Sources are evidence. External sources may be unavailable without invalidating already-authoritative state. Local source paths must be project-relative under `sources/`.

The current-state cache is regenerated if missing, malformed, or stale. Generated artifacts carry source generation plus compiler identity/version. Stale artifacts do not invalidate a project and are regenerated on explicit `COMPILE`.

## Context Handoff and Optional LLMs

One canonical unresolved-register compiler combines project/current-state seams, round-level qualified seams, and current or affected concept seams. Persistence, the runner, session brief, context handoff, recommender, and living document consume that same ordered, deduplicated result.

The context-handoff compiler derives continuity from committed structured state: project identity, mode, current rules, relevant decision provenance, unresolved work, concepts, supersession history, recent TRACE, one next-round recommendation, and session continuity.

The LLM seam is optional and proposal-only. An adapter may propose a `DraftRound`; it cannot commit, supersede, mutate authority, bypass validation, or resolve uncertainty. All core persistence, inspection, manual rounds, answers, synthesis, supersession, concepts, and compilation work with no adapter configured.

## Command Surface

`CommandRunner` supports:

```text
STATE  LEDGER  UNRESOLVED  CONCEPTS  TRACE  ROUND
IMPORT DRAFT <path>
ANSWER  EDIT  PREVIEW  LOCK  ABANDON
SAVE  COMPILE  HELP  END SESSION
```

Project selection is explicit through `PersistentProject.create(...)` or `PersistentProject.resume(...)`; the runner does not silently resume a recent directory.

## Module Ownership

| Module | Responsibility |
|---|---|
| `model.py` | Immutable semantic records and vocabularies |
| `intake.py` | Canonical workspace and rehydration boundary |
| `rounds.py` | Round/questions and bounded owner-answer intake |
| `decisions.py` | Synthesis, ledger, current state, guarded supersession |
| `concepts.py` | Current/affected/history concept lifecycle |
| `trace.py` | Append-only provenance and continuity |
| `codec.py` | Strict plain-data encode/decode contracts |
| `persistence.py` | Manifest, hashes, atomic candidate saves, activation gate |
| `session.py` | Non-authoritative drafts and session metadata |
| `project.py` | Persistent operations, preview, lock, autosave, artifacts |
| `handoff.py` | Context handoff and next-round recommendation |
| `llm.py` | Optional proposal-only adapter protocol |
| `runner.py` | Guided command interface |
| `documents.py` | Pure living-application Markdown renderer |
| `unresolved.py` | Canonical complete unresolved-register compiler |

## Install and Validate

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m design_flow.demo
```

The test suite includes the original semantic regressions plus save/reload, ID stability, TRACE continuation, strict schema/version/hash/generation failures, symmetric supersession and orphan-TRACE attacks, committed-history mutation attempts, canonical unresolved surfaces, command-level draft import, promotion-boundary failure injection, session consistency, draft isolation, optional-LLM absence, and a three-round persisted lifecycle.

GitHub Actions preserves the existing install, full unittest, deterministic demo, and package-build gates on `main`, `codex/**`, and pull requests to `main`.

## Current Limitations

- Single owner and local filesystem only; no collaboration, authentication, or cloud service.
- Manual round construction and declared rule mappings; no general prose interpretation.
- Conflict and concept-impact analysis is explicit rather than inferred.
- One project-format version is supported; there is no migration framework yet.
- Interrupted directory promotion requires owner review; automatic salvage is intentionally absent.
- Application binding remains non-consequence-bearing scaffolding.
- No bundled LLM provider, GUI, plugin ecosystem, or multi-agent governance.

For the semantic laws, see [DESIGN_FLOW_CORE.md](DESIGN_FLOW_CORE.md). For the upstream boundary, see [ARCHITECTURE_DEPENDENCY.md](ARCHITECTURE_DEPENDENCY.md).
