# Persistence, Activation, and Recovery

## Authority Classes

| Class | Files | Meaning |
|---|---|---|
| Authoritative | `manifest.json`, `rounds.json`, `decisions.json`, `concepts.json`, `unresolved.json`, `trace.json` | Defines semantic project truth |
| Operational | `sessions.json`, `working/draft.json`, `sources/index.json` | Durable working metadata; cannot create semantic authority |
| Derived cache | `cache/current_state.json` | Replaceable compilation of authority |
| Derived artifacts | `generated/*.md` | Human/LLM continuity outputs, never inputs to activation |
| Evidence | `sources/` and its metadata | References and optional local copies, not decisions |

Only manifest-registered files participate in activation. Extra files are permitted unless they collide with a reserved path.

## Canonical JSON and Hashes

Registered JSON uses:

- UTF-8;
- sorted object keys;
- compact `,` and `:` separators;
- JSON primitives, arrays, and objects only;
- no NaN/infinity;
- exactly one final newline.

Non-canonical bytes are rejected. All schemas reject unknown fields.

Every registered file uses SHA-256 over its exact canonical bytes. `manifest.json` is self-registered: its expected digest is SHA-256 over the canonical manifest projection with the manifest entry's `content_hash` set to the empty string. The stored manifest then contains that digest.

## Save Generation

Every successful checkpoint increments the project-wide `save_generation`. Every registered file envelope and registry entry must match it. A checkpoint may represent a draft edit or session update; it does not append TRACE or imply a semantic decision revision.

## Candidate Save Pipeline

1. Create a unique temporary sibling of the target directory.
2. Copy unregistered evidence and prior generated material forward.
3. Write the complete new authoritative and operational JSON set.
4. Compile the current-state cache.
5. Write requested generated artifacts.
6. Hash every registered file and construct the manifest self-hash.
7. Load the candidate through the complete activation gate.
8. If the target exists, rename it to a unique sibling backup.
9. Rename the candidate to the target name.
10. Restore the backup if step 9 fails; otherwise attempt to remove it.

The successful step-9 `candidate -> target` rename is the explicit storage commit point. Before it, failure preserves or restores prior authority; a failed rollback preserves the candidate and backup for review. After it, the new canonical target is committed. A step-10 cleanup failure is returned as a recovery warning rather than misreported as a failed promotion, and the leftover backup blocks future ordinary activation.

Same-parent rename is the strongest portable primitive used here. The implementation protects a valid prior directory from ordinary candidate-construction or promotion failure, but does not claim universal power-loss atomicity across the two renames. A crash can leave a candidate or backup. Normal load detects either pattern and stops with a recovery error so an owner can inspect the directories. It never silently chooses or merges them.

## Activation Gate

Activation is all or nothing:

1. Read canonical manifest JSON.
2. Require project format `0.2.0`.
3. Require the exact authoritative and operational registries.
4. Require one positive, consistent save generation.
5. Resolve only safe project-relative registered paths.
6. Verify canonical bytes and SHA-256 for every registered file.
7. Require envelope project ID, semantic role, format, and generation agreement.
8. Reject unknown fields and reconstruct domain records.
9. Validate chronological, unique TRACE IDs and continuation.
10. Validate project/round/question/answer/decision provenance, including question identity without a decision and round purpose/prerequisites.
11. Derive the supersession graph; validate unique edges, replacement status, exact transitive ancestry, bound TRACE, and acyclicity in both directions.
12. Validate concept partitions, decision sources, provenance, and current-source eligibility.
13. Recompile and compare the unresolved register.
14. Compile current design state.
15. Validate session/project identity, referenced rounds, touched/committed subsets, generation bounds, the single-open-session rule, draft schema, and source metadata.
16. Activate the project; regenerate a stale cache afterward if necessary.

Any failure raises `ProjectValidationError`. State before that point is provisional material, not an active project.

For every committed round, activation derives one canonical synthesis sequence from registered decisions whose `source_round` matches that round, preserving ledger registration order. Both `synthesis` and `derived_rules` must equal that sequence exactly. Extra, missing, reordered, duplicated, or rewritten rules are rejected.

`REGISTER_QUESTION` binds question text, type, options, and source round; `RECOMMEND` binds proposed answers, reason, and status. This protects question history even when no decision was synthesized. Round purpose and prerequisites are authoritative fields bound by `REGISTER_ROUND`. `conflicts_detected` is a reserved non-authoritative projection, is required to be empty, and cannot replace the authoritative decision relationship ledger.

## Draft Commit Failure

Round lock clones the active workspace through the same plain-data codecs, applies the complete draft to that clone, and asks the store to validate and promote it. If synthesis, supersession, concept lifecycle, encoding, hashing, validation, or pre-commit promotion fails, the active workspace reference is never replaced. The already-autosaved draft remains available for correction.

Successful candidate-to-target rename commits storage. If only backup cleanup then fails, lock completes against the committed candidate, clears the draft, and exposes a recovery warning. The backup remains deliberately visible so ordinary future activation stops for owner review.

## Unresolved Register

`unresolved.json` is compiled by the same deterministic unresolved-register function used by the runner, session brief, context handoff, next-round recommender, and living document. It combines current design-state seams, committed round-level seams, and current or affected concept seams in stable first-seen order with duplicates removed. Activation recompiles that exact register and requires equality.

## Artifact Staleness

Each generated artifact registry entry records:

- path and semantic role;
- source save generation;
- compiler identity;
- compiler version.

An absent or earlier-generation artifact is `MISSING` or `STALE`, not corrupt authority. `COMPILE` regenerates it from the active committed workspace. A session-only checkpoint can therefore make an artifact stale even when semantic decisions did not change; this is deliberate because the context handoff also includes session continuity.

## Source Evidence

Source metadata has stable IDs, labels, optional external URIs, and optional project-local paths. Local paths must stay under `sources/` and cannot be absolute or traverse upward. An unavailable source is reported as such and does not invalidate previously accepted semantic authority.
