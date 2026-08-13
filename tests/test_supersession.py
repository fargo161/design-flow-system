import unittest

from design_flow import (
    ConflictRelation,
    DecisionStatus,
    DesignFlowMode,
    DesignFlowWorkspace,
    DesignRound,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
)


class SupersessionTests(unittest.TestCase):
    def test_new_decision_becomes_current_and_old_decision_remains_traceable(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="supersession-test",
            name="Supersession Test",
            description="Preserve history when rules change.",
            mode=DesignFlowMode.REFINEMENT,
            authority="Owner",
        )

        for suffix, answer, rules in (
            (
                "old",
                "A",
                {"A": "Movement target is fixed at planning time.", "B": "Movement follows the actor."},
            ),
            (
                "new",
                "B",
                {"A": "Movement target is fixed at planning time.", "B": "Movement follows the actor."},
            ),
        ):
            round_id = f"round-{suffix}"
            question_id = f"question-{suffix}"
            workspace.start_round(DesignRound(round_id, "Movement", "Select target behavior."))
            workspace.add_question(
                round_id,
                Question(
                    question_id=question_id,
                    text="How is the target resolved?",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    options=(QuestionOption("A", "Fixed"), QuestionOption("B", "Follow actor")),
                    recommendation=Recommendation(("A",), "Fixed targets are simple."),
                ),
            )
            workspace.record_owner_answer(round_id, question_id, answer)
            workspace.synthesize_decision(
                round_id,
                question_id,
                decision_id=f"decision-{suffix}",
                scope="movement-targeting",
                rule_mapping=rules,
            )

        workspace.ledger.supersede(
            "decision-old",
            "decision-new",
            notes="The owner replaced fixed targeting with actor-following behavior.",
        )
        state = workspace.state_compiler.compile(workspace.project, workspace.ledger)

        self.assertEqual(DecisionStatus.SUPERSEDED, workspace.ledger.get("decision-old").status)
        self.assertEqual(("decision-old",), workspace.ledger.get("decision-new").supersedes)
        self.assertEqual(("decision-new",), tuple(item.decision_id for item in state.decisions))
        self.assertIn("decision-old", tuple(item.decision_id for item in workspace.ledger.decisions))
        self.assertEqual(ConflictRelation.SUPERSEDES, workspace.ledger.relationships[0].relation)
        self.assertTrue(workspace.ledger.get("decision-old").trace_refs)


if __name__ == "__main__":
    unittest.main()
