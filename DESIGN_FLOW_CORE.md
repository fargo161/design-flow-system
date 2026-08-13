# Design Flow Core

## Identity

Design Flow System v0.2.0 is a persistent, resumable, single-owner design-governance prototype. It turns bounded questions into owner-authored decisions, compiles operative state without erasing history, maintains source-backed core concepts, and produces derived continuity documents.

`DesignFlowWorkspace` remains the canonical semantic integrity boundary. `PersistentProject` adds storage, sessions, non-authoritative drafts, explicit commitment, and compilation around that boundary.

## Design-Flow Unit

```text
QUESTION → OPTIONS → RECOMMENDATION + REASON → OWNER ANSWER
         → SYNTHESIS → DERIVED RULE → TRACE → NEXT TARGET
```

Every stage remains separately inspectable. Convenience orchestration may sequence stages but may not collapse their authority or provenance boundaries.

## Authority Laws

```text
RECOMMENDATION != OWNER DECISION
DRAFT PREVIEW != COMMIT
STORAGE CHECKPOINT != SEMANTIC REVISION
SESSION ID != PROJECT ID
DERIVED DOCUMENT != AUTHORITATIVE STATE
```

Recommendations are advisory history. Only an owner answer supplies the value used by synthesis, and only an explicit lock makes a completed round authoritative. Synthesis uses a declared mapping keyed by the normalized owner value; a caller cannot silently select the rule for a different option.

Qualified input such as `A + C depending on context` retains selections `A` and `C`, the qualifier, unresolved status, and a follow-up discriminator. It is not coerced to one value.

## Project and Session

A project owns the durable semantic lineage: identity, rounds, answers, decisions, relationships, concepts, unresolved state, and TRACE. Project metadata and committed round/question history are immutable snapshots. A session is non-semantic metadata about one bounded operating episode. Resume reuses the one persisted open session; starting a later session continues the same project lineage and never registers a second project authority event.

Session metadata can record timestamps, rounds touched and committed, storage generations, and generated artifacts. Raw transcripts are neither required nor authoritative.

## Draft and Commit Boundary

A `DraftRound` lives in `working/draft.json` and is explicitly non-authoritative. Answering, editing, previewing, autosaving, resuming, or abandoning a draft creates no round, answer, decision, concept, supersession, or TRACE authority.

Preview reconstructs an isolated candidate workspace and reports possible rules, supersessions, affected concepts, unresolved work, or blockers. It never swaps that candidate into the active project.

Lock requires all declared questions to have owner input. The candidate then performs:

```text
round + questions + owner answers
→ synthesis + ledger registration
→ explicit supersession
→ concept registration/revision
→ semantic validation
→ complete validated checkpoint candidate
→ promotion
```

Any failure before storage promotion rejects the candidate, retains the submitted draft, and leaves both in-memory and durable authority unchanged. Once the validated candidate is renamed to the canonical target, storage is committed. A later backup-cleanup failure is reported as a recovery warning; it does not falsely undo the new authority.

## Decisions, Correction, and Current State

The decision ledger retains recommendation, reason, raw owner answer, normalized value, qualifiers, rule source, canonical rule, source round/question, dependencies, unresolved consequences, supersession links, and TRACE references.

The current-state compiler excludes `SUPERSEDED` decisions but never edits the ledger. Historical correction therefore uses:

```text
new owner answer → new decision → guarded SUPERSEDES edge
```

Committed records are immutable snapshots. The in-memory manager performs authorized changes by replacing whole round/question snapshots rather than exposing live mutable history. Drafts remain editable through immutable-replacement draft APIs.

Supersession rejects self-links, ineligible replacements, duplicates, multiple direct replacements, and cycles. Activation derives ancestry from the relationship graph and requires exact agreement among decision status, direct edges, transitive `supersedes` lineage, and one bound TRACE event per edge. A new decision preserves transitive predecessor identity.

## Concepts

A concept can carry stable identity, version, independent status and maturity, scope, definition, ownership boundaries, dependencies, relations, source decisions, unresolved seams, provenance, and TRACE references.

The registry separates settled current, affected/unresolved, and historical concept versions. When a source decision is superseded, dependent settled concepts are quarantined as affected. An explicit revision can connect the replacement decision, preserve original and revision provenance, and return the concept to current state. Deprecation and unresolved retention are also explicit operations.

## TRACE

TRACE is append-only, ordered, locally inspectable provenance. Persisted TRACE IDs are never renumbered; after reload allocation continues above the greatest validated sequence.

Authoritative decisions require matching local synthesis and registration events. Concept sources require valid registered decisions. Supersession requires a corresponding relationship, statuses, lineage, and TRACE event. TRACE details are recursively frozen snapshots; unsafe custom mutable values and cyclic containers are rejected.

Load reconstructs TRACE before rounds, decisions, and concepts so all downstream validation can refer to the actual local history.

## Persistence and Activation

The manifest is the stable entry point and owns one `project_format_version` for the directory. v0.2 supports only format `0.2.0`; unsupported versions fail clearly rather than invoking an implicit migration.

Authoritative JSON includes complete round history, the decision ledger, concepts, unresolved register, and TRACE. Session metadata, drafts, and source evidence metadata are persisted but remain non-semantic. Current state and Markdown are derived.

All registered JSON is deterministic plain data. Unknown fields are rejected. Every registered file records the same save generation and a SHA-256 content hash. The manifest's own hash uses the documented projection in which its self-hash field is empty.

Semantic activation occurs only after schema, hash, generation, role, identity, provenance, lifecycle, cross-reference, unresolved, session-consistency, and compilation checks all pass. There is no partial activation or generated-document fallback.

## Save Semantics

Save generation counts successful storage checkpoints. It is not a decision or concept version and does not append TRACE.

A complete candidate directory is written and validated beside the target. Promotion uses same-parent renames with a backup/restore path. The explicit commit point is the successful candidate-to-target rename. Failures before it preserve or restore prior authority; rollback failure preserves both recovery artifacts. Backup cleanup is post-commit work, so cleanup failure returns a recovery warning while the new target remains canonical and future ordinary activation is blocked for review. This is not described as a universal crash-atomic multi-directory transaction.

See [docs/PERSISTENCE.md](docs/PERSISTENCE.md) for byte-level and recovery details.

## Derived State and Compilers

`cache/current_state.json` is disposable. Load regenerates it when absent, malformed, built by another compiler version, or from another generation.

The living-application renderer and context-handoff compiler operate only on committed state. One canonical unresolved-register compiler combines current-state, round, and current/affected concept seams; persistence, runner, session brief, handoff, recommendation, and the living document all use it. Artifacts record source generation and compiler identity/version. A stale artifact is reportable and regenerable, not a reason to reject the project.

Context handoff includes project identity, mode, current rules, decision provenance, unresolved work, concepts, supersession history, recent TRACE, one advisory next-round recommendation, and session continuity. It never treats raw chat as continuity authority.

## Optional LLM Boundary

An LLM adapter may propose questions, options, recommendations, or an entire `DraftRound`. It may not commit owner decisions, rewrite authority, perform silent supersession, resolve uncertainty autonomously, or bypass the activation gate. No provider package is a runtime dependency; deterministic manual operation remains complete without an adapter.

## Module Boundaries

- `model.py`: semantic records and vocabularies.
- `intake.py`: workspace creation, orchestration, and no-event restoration.
- `rounds.py`: question and bounded owner-answer history.
- `decisions.py`: synthesis, ledger, supersession, current state.
- `concepts.py`: current/affected/history lifecycle.
- `trace.py`: append-only provenance.
- `codec.py`: strict plain-domain serialization.
- `persistence.py`: manifest, hashing, candidate saves, activation.
- `session.py`: session and draft records/codecs.
- `project.py`: persistent operational boundary and all-or-nothing lock.
- `documents.py`: living application renderer.
- `handoff.py`: context handoff and recommendation.
- `llm.py`: optional proposal protocol.
- `runner.py`: command-oriented interaction.
- `unresolved.py`: canonical complete unresolved-register compilation.

## Non-Goals and Deferred Work

v0.2 does not implement collaboration, multi-owner conflict governance, general natural-language interpretation, automatic contradiction solving, automatic concept impact traversal, a format migration system, cloud persistence, authentication, a bundled LLM provider, a GUI, or consequence-bearing application bindings.

Any future broadening must preserve owner authority, immutable history, explicit unresolved state, deterministic persistence, and strict activation.
