import unittest

from design_flow import (
    DecisionStatus,
    DesignFlowMode,
    DesignFlowWorkspace,
    DesignRound,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
    parse_owner_answer,
)


class DecisionFlowTests(unittest.TestCase):
    def test_qualified_answer_is_preserved_and_becomes_follow_up(self) -> None:
        answer = parse_owner_answer(
            "A + C depending on context",
            allowed_values=("A", "B", "C"),
            source_round="round-3",
            source_question="question-3",
        )

        self.assertEqual(("A", "C"), answer.normalized_value)
        self.assertEqual(("depending on context",), answer.qualifiers)
        self.assertEqual(DecisionStatus.UNRESOLVED, answer.status)

        workspace = DesignFlowWorkspace.create(
            project_id="qualified-test",
            name="Qualified Test",
            description="Preserve ambiguity as future design work.",
            mode=DesignFlowMode.REFINEMENT,
            authority="Owner",
        )
        workspace.start_round(DesignRound("round-3", "Modes", "Select contextual modes."))
        workspace.add_question(
            "round-3",
            Question(
                question_id="question-3",
                text="Which modes are valid?",
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=(
                    QuestionOption("A", "Mode A"),
                    QuestionOption("B", "Mode B"),
                    QuestionOption("C", "Mode C"),
                ),
                recommendation=Recommendation(("B",), "B is simplest."),
            ),
        )
        recorded = workspace.record_owner_answer(
            "round-3", "question-3", "A + C depending on context"
        )
        decision = workspace.synthesize_decision(
            "round-3",
            "question-3",
            decision_id="decision-qualified",
            scope="mode-selection",
            rule_mapping={
                ("A", "C"): "Modes A and C apply conditionally.",
            },
        )

        self.assertEqual(answer.normalized_value, recorded.normalized_value)
        self.assertEqual(DecisionStatus.UNRESOLVED, decision.status)
        self.assertIn(
            "Determine the contextual discriminator between A and C.",
            decision.unresolved_consequences,
        )
        state = workspace.state_compiler.compile(workspace.project, workspace.ledger)
        self.assertIn(
            "Determine the contextual discriminator between A and C.",
            state.unresolved,
        )

    def test_compact_round_answers_map_by_question_order(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="compact-test",
            name="Compact Test",
            description="Expand bounded compact owner data.",
            mode=DesignFlowMode.REPAIR,
            authority="Owner",
        )
        workspace.start_round(DesignRound("round", "Repair", "Answer two repair questions."))
        for number in (1, 2):
            workspace.add_question(
                "round",
                Question(
                    question_id=f"q{number}",
                    text=f"Question {number}?",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    options=(QuestionOption("A", "First"), QuestionOption("B", "Second")),
                    recommendation=Recommendation(("A",), "Default advice."),
                ),
            )

        answers = workspace.rounds.record_owner_answers("round", "1B, 2A")

        self.assertEqual(("B",), answers["q1"].normalized_value)
        self.assertEqual(("A",), answers["q2"].normalized_value)
        self.assertEqual(DecisionStatus.OWNER_SELECTED, workspace.rounds.get("round").status)

    def test_yes_no_label_maps_to_its_declared_option_key_and_keeps_qualification(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="yes-no-test",
            name="Yes No Test",
            description="Accept human-facing yes/no labels.",
            mode=DesignFlowMode.DISCOVERY,
            authority="Owner",
        )
        workspace.start_round(DesignRound("round", "Boundary", "Set a bounded exception."))
        workspace.add_question(
            "round",
            Question(
                question_id="q1",
                text="Should the behavior be allowed?",
                question_type=QuestionType.YES_NO,
                options=(QuestionOption("A", "Yes"), QuestionOption("B", "No")),
                recommendation=Recommendation(("B",), "The safe default is no."),
            ),
        )

        answer = workspace.record_owner_answer("round", "q1", "Yes, but only under X")

        self.assertEqual(("A",), answer.normalized_value)
        self.assertEqual(("but only under X",), answer.qualifiers)
        self.assertEqual(DecisionStatus.UNRESOLVED, answer.status)


if __name__ == "__main__":
    unittest.main()
