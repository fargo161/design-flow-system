# PSG Architecture Dependency

```yaml
document_id: DESIGN_FLOW.PSG_DEPENDENCY
status: canonical
relationship_type: upstream_parent_architecture

upstream:
  repository: fargo161/periodic-semantic-grammar
  baseline_commit: 6d1efe5f486082b6372d0ccaeefb85e0c32b13c6

downstream:
  repository: design-flow-system

dependency_direction:
  PSG -> Design Flow System
```

## Relationship

The Design Flow System is a separate downstream application of Periodic Semantic Grammar (PSG). The relationship in v0.1.x is architectural and semantic: this repository adopts PSG-informed distinctions without vendoring PSG, forking PSG, using a submodule, or claiming code-level integration.

PSG is not modified by this repository. The pinned commit identifies the architectural baseline against which this foundation was designed.

## PSG Owns

- Generic semantic identity
- Immutable and versioned semantic records
- Relations, weights, boundaries, and references
- Schemas and bindings
- Validation states and derivation
- TRACE, transfer, and resolution
- Generic explanation and persistence principles

## Design Flow System Owns

- Project intake and design-flow modes
- Design rounds and question objects
- Recommendation and owner-answer records
- Decision synthesis and maturity
- Decision ledgers and current-design-state compilation
- Qualified-answer preservation and unresolved registers
- Explicit conflict relationships and supersession
- Supersession-aware concept current/affected/history state
- Core-concept registration, revision, deprecation, maturity, and provenance lineage
- Living application document generation
- Future implementation, context, specification, and audit compiler boundaries

## Upstream Proposal Rule

> A Design Flow requirement must not be added to PSG core merely because this application needs it.

If implementation work reveals a genuinely generic missing PSG abstraction:

1. Record the requirement in this repository.
2. Label it `UPSTREAM_PSG_PROPOSAL`.
3. Explain why the abstraction is generic rather than Design Flow-specific.
4. Do not modify PSG without separate, explicit authorization.

## Dependency Boundary

```text
PERIODIC SEMANTIC GRAMMAR
    generic upstream semantic architecture
            ↓
DESIGN FLOW SYSTEM
    project-agnostic design-governance application
            ↓
PROJECT-SPECIFIC DESIGN FLOWS
            ↓
LIVING DOCUMENTS AND FUTURE COMPILERS
```

Application requirements remain downstream. A future code dependency must be justified independently and must not be inferred from this architectural relationship.

## README Synchronization

Any change to the upstream repository, baseline commit, dependency direction, division of ownership, or integration maturity is a major semantic change. It requires review of this document, `DESIGN_FLOW_CORE.md`, and `README.md`.
