# Design Flow System

> A project-agnostic design-governance foundation where structured questions produce owner-authored decisions, traceable current rules, persistent core concepts, and living application documents.

## Document Identity

| Field | Current value |
|---|---|
| Authority | Owner answers are authoritative; recommendations are advisory |
| Version | `0.1.0` |
| Maturity | `FOUNDATIONAL` |
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

The v0.1 repository proves this semantic spine with deterministic Python records, an in-memory ledger, current-state compilation, core-concept registration, a Markdown renderer, behavior tests, and a neutral demo.

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

The v0.1 dependency is semantic and architectural. There is no submodule or runtime PSG integration. See [ARCHITECTURE_DEPENDENCY.md](ARCHITECTURE_DEPENDENCY.md).

## Current Concepts

### Canonical / Working

- `OWNER_AUTHORITY` — an owner answer, not a recommendation, controls synthesized state. `IMPLEMENTED`.
- `DECISION_LEDGER` — preserves the full route to a decision. `IMPLEMENTED`.
- `CURRENT_DESIGN_STATE` — compiles operative rules without requiring a reader to reconstruct every round. `IMPLEMENTED`.
- `UNRESOLVED_REGISTER` — preserves ambiguity and exposes follow-up work. `IMPLEMENTED`.
- `SUPERSESSION` — replaces current rules without deleting prior state. `IMPLEMENTED`.
- `CORE_CONCEPT` — retains concept identity, definition, boundaries, relations, status, and provenance. `IMPLEMENTED`.
- `LIVING_APPLICATION_DOCUMENT` — renders current semantic state through a generic binding. `IMPLEMENTED`.
- `TRACE` — records inspectable provenance for semantic operations. `IMPLEMENTED` as a lightweight downstream layer.

### Provisional

- `DISCOVERY`, `REFINEMENT`, and `REPAIR` are first-class project modes. Their records are `IMPLEMENTED`; automated mode-specific planning is `DEFERRED`.
- Conflict relationships are `FOUNDATIONAL`: explicit relations exist, while automatic semantic conflict detection is `DEFERRED`.
- `APPLICATION_BINDING` is `FOUNDATIONAL`: the generic binding seam exists, while project-specific schemas are `DEFERRED`.

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
| `documents.py` | Generic application binding and living Markdown rendering |
| `trace.py` | Append-only local provenance records |
| `demo.py` | Neutral deterministic pipeline proof |

## Current Implemented Capability

- Project identity, source context, authority, state version, unresolved areas, and modes.
- Multiple-choice and yes/no questions with separately stored options and recommendations.
- Owner-answer normalization that retains raw input and qualifications.
- Compact bounded answer intake such as `1B, 2A`.
- Owner-authoritative synthesis and provenance-preserving decision registration.
- Ledger history, current-state compilation, explicit relationship records, and supersession.
- Core-concept records, registration from decisions, and traceable concept revision.
- Generic application bindings and living Markdown document rendering.
- Append-only deterministic TRACE identifiers.
- Behavior-level tests and a deterministic demo.

## Deferred Capability

- Automatic round planning and LLM-driven question generation.
- General free-text answer interpretation and automatic follow-up generation.
- Automatic semantic contradiction or concept-impact analysis.
- Implementation, context, specification, unresolved-register, and audit compiler suite.
- GUI, plugin ecosystem, multi-agent orchestration, project adapters, production persistence, services, authentication, and collaboration.

## Decision Provenance Model

The ledger stores the source round and question, historical recommendation and reason, raw owner input, normalized owner value, qualifiers, synthesized rule, scope, dependencies, unresolved consequences, supersession links, and TRACE references.

The current-state compiler emits non-superseded decisions only. It does not mutate or shorten the ledger.

## Qualified Answers

Input such as `A + C depending on context` becomes selections `A` and `C`, qualifier `depending on context`, status `UNRESOLVED`, and a stored target to determine the contextual discriminator. The system preserves the ambiguity instead of choosing a single option.

This parser is deliberately bounded to declared option keys. It is not a general prose interpreter.

## Supersession Model

Supersession is explicit. The old decision becomes `SUPERSEDED`; the new decision records which decision it replaces; a `supersedes` relationship and TRACE entry are appended; current state uses the new rule; and the historical document section retains the old rule.

## TRACE Model

TRACE records project, round, question, recommendation, owner selection, synthesis, decision, unresolved, supersession, concept, revision, and document-generation events. The implementation applies PSG provenance principles locally and does not claim identity with a PSG code implementation.

No authoritative decision can be registered without synthesis provenance.

## Core Concepts Document Creator

Structured synthesized decisions can register concepts with identity, version, status, maturity, scope, definition, ownership, boundaries, dependencies, relations, source decisions, unresolved seams, supersession, provenance, and TRACE references.

v0.1 does not infer concepts from arbitrary prose.

## Living Application Documents

The generic renderer combines project identity, current state, the concept registry, historical state, unresolved work, and TRACE into Markdown. It records generation as a TRACE event. The output is repeatable derived documentation, not a one-time narrative or a new authority source.

## Install and Run

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m design_flow.demo
```

For a no-install source-tree check, set `$env:PYTHONPATH='src'` and run the same test and demo modules with `python`.

The package has no runtime dependencies beyond Python 3.12 or newer.

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

State is in memory; identifiers are caller-supplied; conflict relations are explicit rather than inferred; the answer parser is bounded; bindings use one generic schema; and maturity transitions beyond synthesis and supersession have no workflow automation.

## Next Legitimate Steps

1. Exercise v0.1 against one real but bounded project flow.
2. Record weaknesses as local decisions or unresolved items.
3. Define persistence only after the record boundaries survive that exercise.
4. Specify one additional compiler or application binding without expanding into a general platform.
5. Raise an `UPSTREAM_PSG_PROPOSAL` only if a missing abstraction is demonstrably generic.

For the deeper canonical architecture, see [DESIGN_FLOW_CORE.md](DESIGN_FLOW_CORE.md).
