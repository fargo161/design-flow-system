import unittest
from dataclasses import replace

from design_flow import (
    Decision,
    DecisionProvenance,
    DecisionStatus,
    DesignFlowMode,
    DesignFlowWorkspace,
    DesignRound,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
)


def workspace_with_question() -> DesignFlowWorkspace:
    workspace = DesignFlowWorkspace.create(
        project_id="trace-integrity",
        name="TRACE Integrity",
        description="Reject forged provenance.",
        mode=DesignFlowMode.REPAIR,
        authority="Owner",
    )
    workspace.start_round(DesignRound("round-1", "Integrity", "Select a rule."))
    workspace.add_question(
        "round-1",
        Question(
            question_id="question-1",
            text="Which rule applies?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=(QuestionOption("A", "First"), QuestionOption("B", "Second")),
            recommendation=Recommendation(("A",), "First is recommended."),
        ),
    )
    workspace.record_owner_answer("round-1", "question-1", "B")
    return workspace


def fabricated_decision(*, decision_id: str = "forged", trace_ref: str) -> Decision:
    return Decision(
        decision_id=decision_id,
        canonical_rule="The second rule applies.",
        authoritative_value=("B",),
        status=DecisionStatus.SYNTHESIZED,
        scope="integrity",
        source_round="round-1",
        source_question="question-1",
        provenance=DecisionProvenance(
            recommendation_was=("A",),
            recommendation_reason="First is recommended.",
            owner_raw_value="B",
            owner_normalized_value=("B",),
            owner_qualifiers=(),
            rule_source_value=("B",),
        ),
        trace_refs=[trace_ref],
    )


class TraceIntegrityTests(unittest.TestCase):
    def test_fake_trace_id_is_refused(self) -> None:
        workspace = workspace_with_question()
        with self.assertRaisesRegex(ValueError, "does not exist"):
            workspace.ledger.register(fabricated_decision(trace_ref="fake-trace"))

    def test_wrong_trace_action_is_refused(self) -> None:
        workspace = workspace_with_question()
        register_question = next(
            record
            for record in workspace.trace.records
            if record.entity_id == "question-1" and record.action.value == "REGISTER_QUESTION"
        )
        with self.assertRaisesRegex(ValueError, "not SYNTHESIZE"):
            workspace.ledger.register(fabricated_decision(trace_ref=register_question.trace_id))

    def test_synthesis_for_wrong_entity_is_refused(self) -> None:
        workspace = workspace_with_question()
        valid = workspace.synthesizer.synthesize(
            workspace.rounds.get("round-1"),
            "question-1",
            decision_id="actual-decision",
            scope="integrity",
            rule_mapping={"A": "The first rule applies.", "B": "The second rule applies."},
        )
        forged = fabricated_decision(decision_id="other-decision", trace_ref=valid.trace_refs[0])
        with self.assertRaisesRegex(ValueError, "does not belong"):
            workspace.ledger.register(forged)

    def test_mismatched_owner_value_is_refused(self) -> None:
        workspace = workspace_with_question()
        decision = workspace.synthesizer.synthesize(
            workspace.rounds.get("round-1"),
            "question-1",
            decision_id="decision",
            scope="integrity",
            rule_mapping={"A": "The first rule applies.", "B": "The second rule applies."},
        )
        decision = replace(decision, authoritative_value=("A",))
        with self.assertRaisesRegex(ValueError, "authoritative value"):
            workspace.ledger.register(decision)

    def test_canonical_rule_tampering_is_refused(self) -> None:
        workspace = workspace_with_question()
        decision = workspace.synthesizer.synthesize(
            workspace.rounds.get("round-1"),
            "question-1",
            decision_id="decision",
            scope="integrity",
            rule_mapping={"A": "The first rule applies.", "B": "The second rule applies."},
        )
        decision = replace(decision, canonical_rule="The first rule applies.")
        with self.assertRaisesRegex(ValueError, "canonical_rule"):
            workspace.ledger.register(decision)

    def test_concept_registration_refuses_fabricated_source_provenance(self) -> None:
        workspace = workspace_with_question()
        forged = fabricated_decision(trace_ref="fake-trace")
        with self.assertRaisesRegex(ValueError, "does not exist"):
            workspace.register_concept_from_decision(
                forged,
                concept_id="forged.concept",
                canonical_name="FORGED_CONCEPT",
                definition="This concept must not register.",
            )

    def test_rule_mapping_must_declare_the_owner_selected_value(self) -> None:
        workspace = workspace_with_question()
        with self.assertRaisesRegex(ValueError, "authoritative owner value"):
            workspace.synthesize_decision(
                "round-1",
                "question-1",
                decision_id="decision",
                scope="integrity",
                rule_mapping={"A": "The first rule applies."},
            )


if __name__ == "__main__":
    unittest.main()
