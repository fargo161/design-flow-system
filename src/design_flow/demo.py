"""Deterministic end-to-end demonstration of owner authority and provenance."""

from __future__ import annotations

from .intake import DesignFlowWorkspace
from .model import (
    DesignFlowMode,
    DesignRound,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
)


def build_demo() -> tuple[DesignFlowWorkspace, str]:
    workspace = DesignFlowWorkspace.create(
        project_id="neutral-movement-demo",
        name="Neutral Movement Demo",
        description=(
            "A neutral proof that owner-authored decisions, not assistant advice, "
            "control the current design state."
        ),
        mode=DesignFlowMode.DISCOVERY,
        authority="The project owner is the design authority.",
    )
    workspace.start_round(
        DesignRound(
            round_id="round.movement-targeting",
            topic="Movement Targeting",
            purpose="Choose the identity used by relational movement.",
        )
    )
    workspace.add_question(
        "round.movement-targeting",
        Question(
            question_id="question.actor-identity",
            text="Should relational movement target an actor identity?",
            question_type=QuestionType.YES_NO,
            options=(QuestionOption("A", "Yes"), QuestionOption("B", "No")),
            recommendation=Recommendation(
                proposed_answer=("A",),
                reason="Preserves player intention if the actor moves.",
            ),
        ),
    )
    workspace.record_owner_answer(
        "round.movement-targeting",
        "question.actor-identity",
        "B",
    )
    rules = {
        "A": "Relational movement targets actor identity.",
        "B": "Relational movement does not target actor identity.",
    }
    decision = workspace.synthesize_decision(
        "round.movement-targeting",
        "question.actor-identity",
        decision_id="decision.movement-target-identity",
        scope="movement-targeting",
        rule_mapping=rules,
    )
    workspace.register_concept_from_decision(
        decision,
        concept_id="movement.target_identity",
        canonical_name="MOVEMENT_TARGET_IDENTITY",
        definition=decision.canonical_rule,
        owns=("the identity referenced by relational movement",),
        does_not_own=("pathfinding", "movement speed"),
        boundaries=("Only relational movement is in scope.",),
    )
    workspace.record_application_document_generation()
    markdown = workspace.render_application_document()
    return workspace, markdown


def main() -> None:
    workspace, markdown = build_demo()
    question = workspace.rounds.get("round.movement-targeting").question("question.actor-identity")
    decision = workspace.ledger.get("decision.movement-target-identity")

    assert question.recommendation.proposed_answer == ("A",)
    assert question.owner_answer is not None
    assert question.owner_answer.normalized_value == ("B",)
    assert decision.authoritative_value == ("B",)
    assert decision.provenance.recommendation_was == ("A",)
    assert "MOVEMENT_TARGET_IDENTITY" in markdown
    assert decision.trace_refs

    print("DESIGN FLOW SYSTEM v0.1.1 — DETERMINISTIC DEMO")
    print("Recommendation preserved: A")
    print("Owner answer preserved: B")
    print(f"Authoritative decision: {decision.authoritative_value[0]}")
    print(f"Canonical rule: {decision.canonical_rule}")
    print(f"Core concepts registered: {len(workspace.concepts.concepts)}")
    print(f"TRACE records: {len(workspace.trace.records)}")
    print("Living application document rendered: YES")
    print("\n--- LIVING APPLICATION DOCUMENT ---\n")
    print(markdown)


if __name__ == "__main__":
    main()
