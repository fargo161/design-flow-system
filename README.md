# Design Flow System

> A project-agnostic design-governance foundation where structured questions produce owner-authored decisions, traceable current rules, persistent core concepts, and living application documents.

## Document Identity

| Field | Current value |
|---|---|
| Authority | Owner answers are authoritative; recommendations are advisory |
| Version | `0.1.1` |
| Maturity | `STABILIZED FOUNDATION` |
| Repository role | PSG-linked downstream application |
| Upstream | `fargo161/periodic-semantic-grammar` |
| PSG baseline | `6d1efe5f486082b6372d0ccaeefb85e0c32b13c6` |
| Runtime | Python 3.12+, standard library |

This README is a synchronized orientation surface. It derives its claims from the architecture and implementation; it is not an independent design authority.

## What This Project Is

The Design Flow System turns bounded design questions into explicit owner choices and preserves the path from advice to current state:

```text
QUESTION → OPTIONS → RECOMMENDATION → REASON → OWNER ANSWER
         → SYNTHESIS → DERIVED RULE → TRACE → NEXT DESIGN TARGET
```

The v0.1.1 repository stabilizes this semantic spine with deterministic Python records, an in-memory ledger, current-state compilation, supersession-aware concepts, a pure Markdown renderer, adversarial behavior tests, and a neutral demo.

## What It Is Not

It is not PSG core, a questionnaire generator by itself, an autonomous design authority, a mature product UI, an LLM service, a production ontology engine, or a silent contradiction resolver. It neither modifies nor vendors PSG.

## Authority

```text
ASSISTANT RECOMMENDATION != OWNER DECISION
```

Recommendations and reasons are stored as advisory history. Owner answers are stored independently. Synthesis receives the owner answer, and the resulting decision preserves the earlier recommendation as provenance.

If advice proposes `A` and the owner selects `B`, current state uses `B`. The test suite treats that behavior as a regression-protected invariant.

## Upstream PSG Relationship

PSG supplies the generic parent architecture: identity, version, status, relations, boundaries, references, validation, derivation, TRACE, transfer, and explanation principles. Design Flow owns project intake, question rounds, advice, owner choices, synthesis, ledgers, current state, supersession, concepts, and living documents.

The v0.1.x dependency is semantic and architectural. There is no submodule or runtime PSG integration. See [ARCHITECTURE_DEPENDENCY.md](ARCHITECTURE_DEPENDENCY.md).

## Current Concepts

### Canonical / Working

- `OWNER_AUTHORITY` — an owner answer, not a recommendation, controls synthesized state. `IMPLEMENTED`.
- `DECISION_LEDGER` — preserves the full route to a decision. `IMPLEMENTED`.
- `CURRENT_DESIGN_STATE` — compiles operative rules without requiring a reader to reconstruct every round. `IMPLEMENTED`.
- `UNRESOLVED_REGISTER` — preserves ambiguity and exposes follow-up work. `IMPLEMENTED`.
- `SUPERSESSION` — replaces current rules without deleting prior state and quarantines dependent concepts until explicitly resolved. `IMPLEMENTED`.
- `CORE_CONCEPT` — retains concept identity, definition, boundaries, relations, status, and provenance. `IMPLEMENTED`.
- `LIVING_APPLICATION_DOCUMENT` — purely renders one coherent current semantic state. `IMPLEMENTED`.
- `TRACE` — records inspectable provenance for semantic operations. `IMPLEMENTED` as a lightweight downstream layer.

### Provisional

- `DISCOVERY`, `REFINEMENT`, and `REPAIR` are first-class project modes. Their records are `IMPLEMENTED`; automated mode-specific planning is `DEFERRED`.
- Conflict relationships are `FOUNDATIONAL`: explicit relations exist, while automatic semantic conflict detection is `DEFERRED`.
- `APPLICATION_BINDING` is `FOUNDATIONAL SCAFFOLDING` and is not consequence-bearing. Records can be constructed, but rendering does not yet use them for placement or section semantics. Project-specific schemas remain `DEFERRED`.

### Unresolved

The final product name, exact mature lifecycle vocabulary, persistence format, conflict algorithm, round-priority model, automatic follow-up behavior, LLM interaction layer, recommendation-abstention mechanics, application-schema system, impact traversal, multi-agent governance, compiler suite, UI, and collaborative workflow remain `UNRESOLVED`.

## System Architecture

```text
PROJECT INTAKE
      ↓
ROUND + QUESTIONS + ADVICE
      ↓
OWNER ANSWER INTAKE
      ↓
DECISION SYNTHESIS
      ↓
┌──────────────────┬──────────────────────┐
│ DECISION LEDGER  │ CURRENT DESIGN STATE │
└──────────────────┴──────────────────────┘
                 ↓
       CORE CONCEPT REGISTRY
                 ↓
        APPLICATION BINDING
                 ↓
   LIVING APPLICATION DOCUMENT
```

### Module Relations

| Module | Implemented ownership |
|---|---|
| `model.py` | Records, modes, statuses, relations, and actions |
| `intake.py` | Project intake and small orchestration facade |
| `rounds.py` | Round registration, questions, compact and qualified answer intake |
| `decisions.py` | Synthesis, ledger, relationships, supersession, current state |
| `concepts.py` | Core-concept registration and traceable revision |
| `documents.py` | Binding scaffolding, pure living Markdown rendering, explicit generation events |
| `trace.py` | Append-only local provenance records |
| `demo.py` | Neutral deterministic pipeline proof |

## Current Implemented Capability

- Project identity, source context, authority, state version, unresolved areas, and modes.
- Multiple-choice and yes/no questions with separately stored options and recommendations.
- Owner-answer normalization that retains raw input and qualifications.
- Compact bounded answer intake such as `1B, 2A`.
- Owner-authoritative synthesis through declared owner-value-to-rule mappings.
- Strict synthesis TRACE validation for decision registration, current state, concept sources, and revisions.
- Ledger history, current-state compilation, explicit relationships, and supersession-driven concept quarantine.
- Separate settled-current, affected/unresolved, and historical concept registries.
- Core-concept registration, explicit revise/deprecate/unresolved paths, and version-correct provenance lineage.
- Distinct concept status and maturity vocabularies.
- Non-consequence-bearing binding scaffolding and pure, byte-deterministic living Markdown rendering.
- Append-only deterministic TRACE identifiers.
- Behavior-level tests and a deterministic demo.

## Deferred Capability

- Automatic round planning and LLM-driven question generation.
- General free-text answer interpretation and automatic follow-up generation.
- Automatic semantic contradiction or concept-impact analysis.
- Implementation, context, specification, unresolved-register, and audit compiler suite.
- GUI, plugin ecosystem, multi-agent orchestration, project adapters, production persistence, services, authentication, and collaboration.

## Decision Provenance Model

The ledger stores the source round and question, historical recommendation and reason, raw owner input, normalized owner value, qualifiers, declared owner-value-to-rule source, synthesized rule, scope, dependencies, unresolved consequences, supersession links, and TRACE references. Authoritative decisions are immutable snapshots; registration and supersession replace ledger-owned records rather than exposing writable semantic state through ledger or current-state accessors.

Registration validates the cited local synthesis record by existence, action, entity type and identity, source round and question, authoritative value, recommendation, canonical rule, and applicable status. A nonempty or fabricated reference is insufficient.

The current-state compiler emits non-superseded decisions only. It does not mutate or shorten the ledger.

## Qualified Answers

Input such as `A + C depending on context` becomes selections `A` and `C`, qualifier `depending on context`, status `UNRESOLVED`, and a stored target to determine the contextual discriminator. The system preserves the ambiguity instead of choosing a single option.

This parser is deliberately bounded to declared option keys. It is not a general prose interpreter.

## Supersession Model

Supersession is explicit and acyclic. Self-supersession, replacement by a non-current decision, duplicate edges, and graph-closing cycles are rejected before state changes. `SUPERSEDES` relationships can be created only by the guarded `supersede()` operation; direct relationship registration remains available for the other declared relation kinds. A valid chain such as A -> B -> C retains its ordered ancestry. The old decision becomes `SUPERSEDED`; the new decision records what it replaces; a `supersedes` relationship and TRACE entry are appended; and current decision state uses the new rule. Any settled concept sourced from the old decision is immediately moved into affected/unresolved state. It can return to current state only through an explicit revision, or leave operative state through deprecation. Old decisions and concept versions remain historical.

## TRACE Model

TRACE records project, round, question, recommendation, owner selection, synthesis, decision, unresolved, supersession, concept, revision, and document-generation events. The implementation applies PSG provenance principles locally and does not claim identity with a PSG code implementation.

No authoritative decision can be accepted without matching synthesis proof in the actual local TRACE. Concept registration and revision additionally require the source decision's ledger-registration event.

TRACE records are immutable snapshots. Details admit only `None`, primitive booleans/numbers/strings, safely normalized enums, and recursively frozen mappings, lists/tuples, and sets/frozensets. Caller-owned containers are copied on ingress; unsupported custom values and cyclic containers are rejected rather than stored by reference.

## Core Concepts Document Creator

Structured synthesized decisions can register concepts with identity, version, status, maturity, scope, definition, ownership, boundaries, dependencies, relations, source decisions, unresolved seams, supersession, provenance, and TRACE references. Status (`CURRENT`, `UNRESOLVED`, `DEPRECATED`, `SUPERSEDED`) is independent from maturity (`PROPOSED`, `DEFINED`, `TESTED`, `STABLE`, `DISPUTED`, `DEPRECATED`).

Revision provenance retains the original source and revision history while making the replacement decision the current version's displayed source.

Core-concept records and their nested provenance are immutable snapshots. All current, affected, and historical state transitions occur through registry operations such as registration, affected marking, revision, and deprecation; accessors never expose mutable semantic state.

v0.1.1 does not infer concepts from arbitrary prose.

## Integrity Boundary

`DesignFlowWorkspace` is the canonical integration boundary for complete v0.1.1 behavior. It owns the shared TRACE and wires decision supersession to concept invalidation. The exported ledger, registry, renderer, and other lower-level classes remain composable primitives, but direct callers are responsible for equivalent cross-module wiring and therefore do not automatically receive the full workspace invariant.

## Living Application Documents

The generic renderer combines project identity, settled current concepts, current decisions, affected/unresolved concepts, historical state, and TRACE into Markdown. Rendering is pure: two renders of unchanged semantic state are byte-identical. When event provenance is desired, callers explicitly record document generation before rendering. The binding object remains non-consequence-bearing scaffolding.

## Install and Run

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m design_flow.demo
```

For a no-install source-tree check, set `$env:PYTHONPATH='src'` and run the same test and demo modules with `python`.

The package has no runtime dependencies beyond Python 3.12 or newer.

## Continuous Integration

GitHub Actions CI runs the full unittest suite, deterministic demo, and package build on pushes to `main` and `codex/**` branches, and on pull requests targeting `main`.

## Repository Layout

```text
design-flow-system/
├── README.md
├── ARCHITECTURE_DEPENDENCY.md
├── DESIGN_FLOW_CORE.md
├── pyproject.toml
├── src/design_flow/
├── tests/
└── docs/
    ├── context/
    ├── decisions/
    ├── examples/
    └── audits/
```

## README Synchronization

> Any change to canonical terminology, system identity, module ownership, maturity, major architecture, supersession, unresolved-work status, or upstream dependency must trigger a README review and update when relevant.

- A major semantic change requires a README update.
- A minor implementation detail requires one only when orientation materially changes.

Documentation and code must remain symmetrical: claims about authority, ambiguity, supersession, current state, and provenance require matching executable behavior.

## Current Limitations

State is in memory; identifiers are caller-supplied; conflict relations are explicit rather than inferred; direct low-level composition requires manual integrity wiring; affected concepts require explicit owner resolution; the answer parser is bounded; binding records do not yet affect output; and maturity transitions are explicit rather than automated.

## Next Legitimate Steps

1. Exercise v0.1.1 against one real but bounded project flow.
2. Record weaknesses as local decisions or unresolved items.
3. Define persistence only after the record boundaries survive that exercise.
4. Specify one additional compiler or application binding without expanding into a general platform.
5. Raise an `UPSTREAM_PSG_PROPOSAL` only if a missing abstraction is demonstrably generic.

For the deeper canonical architecture, see [DESIGN_FLOW_CORE.md](DESIGN_FLOW_CORE.md).
