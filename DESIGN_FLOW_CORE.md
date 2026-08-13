# Design Flow Core

## Identity

The Design Flow System is a project-agnostic design-governance foundation. It turns bounded questions into owner-authored decisions, compiles operative current state without erasing history, registers persistent core concepts, and renders a living application document.

Version `0.1.1` is a semantically stabilized foundation. It is not the mature product.

## Design-Flow Unit

```text
QUESTION
    ↓
OPTIONS
    ↓
RECOMMENDATION + REASON
    ↓
OWNER ANSWER
    ↓
SYNTHESIS
    ↓
DERIVED DESIGN RULE
    ↓
TRACE / CONTEXT UPDATE
    ↓
NEXT QUESTION OR ROUND
```

Each stage has a separate record or operation. Convenience APIs may orchestrate the stages, but they may not collapse their authority or provenance boundaries.

## Authority Law

```text
ASSISTANT RECOMMENDATION != OWNER DECISION
```

A recommendation is advisory and remains historically inspectable. Only an owner answer can supply the authoritative value used by synthesis. A decision records both the authoritative value and the recommendation that preceded it.

Synthesis selects the canonical rule from a declared mapping keyed by the normalized owner value. A caller cannot silently return the rule for `A` when the authoritative value is `B`. This is bounded consistency, not free-text truth checking.

Decision registration rejects state unless an actual local `SYNTHESIZE` record matches the decision identity, source, owner value, recommendation, canonical rule, and applicable status.

## Decision Lifecycle

- `OPEN`: no owner answer yet.
- `PROPOSED`: advice exists but has not been selected.
- `OWNER_SELECTED`: the owner made a bounded, unqualified selection.
- `SYNTHESIZED`: the selected answer became an operative rule.
- `TESTED`: reserved for an exercised implementation.
- `RATIFIED`: reserved for post-review acceptance.
- `UNRESOLVED`: the answer or consequence remains intentionally qualified.
- `SUPERSEDED`: a later decision replaced the rule; history remains.

`UNRESOLVED` is not invalid. `SUPERSEDED` is not deleted.

## Ledger and Current State

The decision ledger answers, “How did we arrive here?” It retains each recommendation, reason, raw owner answer, normalized owner value, qualifiers, synthesis, relationship, and TRACE reference.

The current-state compiler answers, “What has actually been decided now?” It includes every operative decision except those marked `SUPERSEDED`. Each output decision retains its source round and question.

```text
DECISION LEDGER                 CURRENT DESIGN STATE
full history                   operative rules
recommendations                owner-authoritative values
superseded records             unresolved consequences
provenance                     source references
```

The compiler is a view over the ledger. It does not rewrite ledger history.

## Qualified and Unresolved Answers

The deterministic v0.1.1 parser recognizes declared option keys. Anything beyond those keys is retained as qualification.

```text
A + C depending on context
        ↓
normalized: [A, C]
qualifier: depending on context
status: UNRESOLVED
follow-up: Determine the contextual discriminator between A and C.
```

The parser does not claim general natural-language interpretation. Missing precision becomes future design work.

## Conflict and Supersession

The ledger supports explicit relations:

- `compatible`
- `potential_conflict`
- `supersedes`
- `unresolved_conflict`

There is no universal contradiction solver. A caller or owner declares a relationship. When supersession is authorized, the ledger marks the earlier decision `SUPERSEDED`, points the newer decision back to it, retains both records, and appends a TRACE event.

The workspace wires supersession to the concept registry. Any settled concept sourced from the replaced decision moves out of current state and into affected/unresolved state. The owner or caller must explicitly revise, deprecate, or retain it as unresolved. The system does not guess which semantic repair is correct.

## TRACE

The local TRACE is an append-only sequence of inspectable records. It applies PSG provenance principles but is not represented as PSG’s code-level TRACE implementation.

Implemented actions include project, round, and question registration; recommendation; owner selection; synthesis; decision registration; unresolved marking; supersession; concept registration, affected marking, revision, deprecation; and explicit document-generation recording.

No authoritative decision may be accepted without a matching synthesis record in the actual local TRACE. Concept sources additionally require a matching ledger-registration event. A fake ID, wrong action, wrong entity, mismatched owner value, or synthesized-but-unregistered concept source is rejected.

## Core Concepts

A core concept preserves more than a heading. Its record can carry stable identity, version, status, maturity, scope, definition, ownership boundaries, dependencies, relations, source decisions, unresolved seams, supersession, provenance, and TRACE references.

Concept status and maturity use distinct vocabularies. The registry separates settled current concepts, affected/unresolved concepts, and historical versions. Revision provenance retains an original source, current-version source, and revision lineage.

v0.1.1 registers concepts from structured decisions. It does not infer ontologies from arbitrary prose. A concept revision retains a superseded historical record.

## Application Binding and Living Documents

```text
CORE CONCEPT
    ↓
APPLICATION SCHEMA
    ↓
DOCUMENT BINDING
    ↓
HUMAN-READABLE APPLICATION SECTION
```

`ApplicationBinding` is foundational scaffolding only. It can describe a future mapping but does not yet alter placement or document consequences; project-specific binding remains deferred.

The current pure renderer emits document identity, authority, settled concepts, current decisions, affected/unresolved concepts, historical state, and TRACE. It does not mutate TRACE. Two unchanged renders are byte-identical. A separate explicit operation may record `GENERATE_DOCUMENT` before rendering. Markdown is derived presentation, not an independent authority source.

## Operating Modes

- `DISCOVERY`: build foundations for an early or unclear project.
- `REFINEMENT`: sharpen an existing design without presuming failure.
- `REPAIR`: begin from identified defects or audit findings.

The mode is represented in project state and TRACE. Automated mode-specific round planning is deferred.

## Module Boundaries

- `model.py`: semantic records and vocabularies.
- `intake.py`: project intake and orchestration facade.
- `rounds.py`: round/question registration and bounded answer intake.
- `decisions.py`: mapped synthesis, ledger, relationships, supersession, current state.
- `concepts.py`: current/affected/history registries and traceable resolution.
- `documents.py`: binding scaffolding, pure rendering, explicit generation events.
- `trace.py`: append-only local provenance.
- `demo.py`: deterministic end-to-end proof.

## Future Compiler Boundary

`DocumentCompiler` reserves a small interface boundary for future current-context, implementation-prompt, design-specification, audit, and unresolved-register compilers. Only the living application document renderer is implemented.

## Non-Goals

This foundation does not include a GUI, runtime LLM dependency, arbitrary-prose parsing, automatic ontology discovery, universal contradiction solving, full impact traversal, production persistence, cloud services, collaboration, multi-agent orchestration, project-specific adapters, or full PSG library integration.

## Documentation Symmetry and Synchronization

The code and documentation must express the same laws. Canonical terminology, identity, ownership, maturity, architecture, supersession, unresolved status, and upstream dependency changes require a README review. Minor implementation changes require a README update only when the orientation surface materially changes.
