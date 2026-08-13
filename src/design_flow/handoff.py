"""Deterministic continuity compilers over committed project state."""

from __future__ import annotations

from dataclasses import dataclass

from .intake import DesignFlowWorkspace
from .model import ConflictRelation, DecisionStatus
from .session import SessionRecord
from .unresolved import compile_unresolved_register


@dataclass(slots=True, frozen=True)
class RoundRecommendation:
    topic: str
    reason: str


def recommend_next_round(workspace: DesignFlowWorkspace) -> RoundRecommendation:
    """Recommend one next topic without starting it or creating authority."""

    if workspace.concepts.affected:
        names = ", ".join(item.concept_id for item in workspace.concepts.affected)
        return RoundRecommendation(
            "Resolve affected concepts",
            f"Supersession left explicit concept work: {names}.",
        )
    unresolved = compile_unresolved_register(workspace)
    if unresolved:
        return RoundRecommendation(
            "Resolve the oldest open seam",
            f"The unresolved register begins with: {unresolved[0]}",
        )
    return RoundRecommendation(
        "Refine the next owner-selected boundary",
        "The committed state is coherent; the owner can choose the next design boundary.",
    )


def compile_context_handoff(
    workspace: DesignFlowWorkspace,
    sessions: tuple[SessionRecord, ...] = (),
) -> str:
    """Compile compact but sufficient continuity from structured authority."""

    state = workspace.state_compiler.compile(workspace.project, workspace.ledger)
    unresolved = compile_unresolved_register(workspace)
    recommendation = recommend_next_round(workspace)
    active = [item for item in state.decisions if item.status is not DecisionStatus.SUPERSEDED]
    supersessions = [
        item
        for item in workspace.ledger.relationships
        if item.relation is ConflictRelation.SUPERSEDES
    ]
    recent_trace = workspace.trace.records[-12:]
    last_session = sessions[-1] if sessions else None

    lines = [
        "# Design Flow Context Handoff",
        "",
        "## Project",
        "",
        f"- Project ID: `{workspace.project.project_id}`",
        f"- Name: {workspace.project.name}",
        f"- Mode: `{workspace.project.current_mode.value}`",
        f"- Authority: {workspace.project.authority}",
        "",
        "## Current Design State",
        "",
    ]
    lines.extend(
        f"- `{item.decision_id}`: {item.canonical_rule} ({item.status.value})"
        for item in active
    )
    if not active:
        lines.append("- No committed decisions yet.")

    lines.extend(["", "## Relevant Decision History", ""])
    for item in workspace.ledger.decisions:
        qualifier = "; ".join(item.provenance.owner_qualifiers) or "none"
        owner_value = ", ".join(item.authoritative_value) or "unparsed"
        recommended = ", ".join(item.provenance.recommendation_was) or "none"
        lines.extend(
            [
                f"- `{item.decision_id}` [{item.status.value}] {item.canonical_rule}",
                f"  - Owner value: {owner_value}; raw: {item.provenance.owner_raw_value}",
                f"  - Owner qualifier: {qualifier}",
                f"  - Prior recommendation: {recommended} — "
                f"{item.provenance.recommendation_reason}",
            ]
        )
    if not workspace.ledger.decisions:
        lines.append("- No committed decision history.")

    lines.extend(["", "## Unresolved Register", ""])
    lines.extend(f"- {item}" for item in unresolved)
    if not unresolved:
        lines.append("- None.")

    lines.extend(["", "## Core Concepts", ""])
    concepts = (*workspace.concepts.concepts, *workspace.concepts.affected)
    lines.extend(
        f"- `{item.concept_id}` {item.canonical_name} v{item.version}: "
        f"{item.definition} ({item.status.value}/{item.maturity.value})"
        for item in concepts
    )
    if not concepts:
        lines.append("- None registered.")

    lines.extend(["", "## Supersession History", ""])
    lines.extend(
        f"- `{item.earlier_decision}` → `{item.later_decision}`: {item.notes}"
        for item in supersessions
    )
    if not supersessions:
        lines.append("- None.")

    lines.extend(["", "## Recent TRACE", ""])
    lines.extend(
        f"- `{item.trace_id}` {item.action.value} {item.entity_type} `{item.entity_id}`"
        for item in recent_trace
    )

    lines.extend(
        [
            "",
            "## Next-Round Recommendation",
            "",
            f"- Topic: {recommendation.topic}",
            f"- Why: {recommendation.reason}",
            "- Status: advisory only; no round has been started.",
            "",
            "## Session Continuity",
            "",
        ]
    )
    if last_session is None:
        lines.append("- No persisted session metadata.")
    else:
        lines.extend(
            [
                f"- Last session: `{last_session.session_id}`",
                f"- Started: {last_session.started_at}",
                f"- Ended: {last_session.ended_at or 'open'}",
                f"- Rounds committed: {', '.join(last_session.rounds_committed) or 'none'}",
            ]
        )
    return "\n".join(lines) + "\n"
