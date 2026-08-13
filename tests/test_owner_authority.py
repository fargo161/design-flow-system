import unittest

from design_flow import (
    DesignFlowMode,
    DesignFlowWorkspace,
    DesignRound,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
)


class OwnerAuthorityTests(unittest.TestCase):
    def test_owner_answer_controls_current_state_and_advice_remains_history(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="authority-test",
            name="Authority Test",
            description="Verify that owner authority is preserved.",
            mode=DesignFlowMode.DISCOVERY,
            authority="Owner answers are authoritative.",
        )
        workspace.start_round(DesignRound("round-1", "Targeting", "Select targeting behavior."))
        question = workspace.add_question(
            "round-1",
            Question(
                question_id="question-1",
                text="Which target model applies?",
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=(QuestionOption("A", "Actor"), QuestionOption("B", "Position")),
                recommendation=Recommendation(("A",), "Actor targets preserve identity."),
            ),
        )

        workspace.record_owner_answer("round-1", "question-1", "B")
        decision = workspace.synthesize_decision(
            "round-1",
            "question-1",
            decision_id="decision-1",
            scope="targeting",
            rule_mapping={
                "A": "Movement targets an actor.",
                "B": "Movement targets a position.",
            },
        )
        state = workspace.state_compiler.compile(workspace.project, workspace.ledger)

        self.assertEqual(("A",), question.recommendation.proposed_answer)
        self.assertEqual(("B",), question.owner_answer.normalized_value)
        self.assertEqual(("B",), decision.authoritative_value)
        self.assertEqual("Movement targets a position.", decision.canonical_rule)
        self.assertEqual(("A",), decision.provenance.recommendation_was)
        self.assertEqual("Which target model applies?", decision.provenance.question_text)
        self.assertEqual(("A", "B"), tuple(item.key for item in decision.provenance.options))
        self.assertEqual((decision,), state.decisions)
        self.assertEqual("round-1", state.decisions[0].source_round)
        self.assertEqual("question-1", state.decisions[0].source_question)

    def test_decision_registration_rejects_missing_synthesis_trace(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="trace-test",
            name="Trace Test",
            description="Verify provenance enforcement.",
            mode=DesignFlowMode.DISCOVERY,
            authority="Owner",
        )
        from design_flow import Decision, DecisionProvenance, DecisionStatus

        untraced = Decision(
            decision_id="untraced",
            canonical_rule="A rule without evidence.",
            authoritative_value=("A",),
            status=DecisionStatus.SYNTHESIZED,
            scope="test",
            source_round="missing",
            source_question="missing",
            provenance=DecisionProvenance(("B",), "Advice", "A", ("A",), ()),
        )
        with self.assertRaisesRegex(ValueError, "provenance"):
            workspace.ledger.register(untraced)


if __name__ == "__main__":
    unittest.main()
