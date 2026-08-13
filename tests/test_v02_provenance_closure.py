from __future__ import annotations

from design_flow import (
    DraftDecisionPlan,
    DraftQuestion,
    DraftRound,
    PersistentProject,
    ProjectStore,
    ProjectValidationError,
    QuestionOption,
    QuestionType,
    Recommendation,
)
from tests.test_v02_integrity_repair import IntegrityCase
from tests.test_v02_persistence import simple_draft


def two_decision_draft() -> DraftRound:
    return DraftRound.create(
        draft_id="draft-two",
        round_id="round-two",
        topic="Two boundaries",
        purpose="Choose two ordered boundaries.",
        prerequisites=("Foundation accepted",),
        questions=(
            DraftQuestion(
                "question-1",
                "Which first boundary?",
                QuestionType.MULTIPLE_CHOICE,
                (QuestionOption("A", "Alpha"), QuestionOption("B", "Beta")),
                Recommendation(("A",), "Alpha is the smaller first boundary."),
            ),
            DraftQuestion(
                "question-2",
                "Which second boundary?",
                QuestionType.MULTIPLE_CHOICE,
                (QuestionOption("A", "Gamma"), QuestionOption("B", "Delta")),
                Recommendation(("B",), "Delta preserves the second seam."),
            ),
        ),
        decisions=(
            DraftDecisionPlan.create(
                question_id="question-1",
                decision_id="decision-1",
                scope="first",
                rule_mapping={"A": "Use alpha.", "B": "Use beta."},
            ),
            DraftDecisionPlan.create(
                question_id="question-2",
                decision_id="decision-2",
                scope="second",
                rule_mapping={"A": "Use gamma.", "B": "Use delta."},
            ),
        ),
    )


class CommittedHistoryProvenanceTests(IntegrityCase):
    def commit_two(self) -> None:
        self.project.start_session("two-decisions")
        self.project.set_draft(two_decision_draft())
        self.project.answer_draft("question-1", "A")
        self.project.answer_draft("question-2", "B")
        self.project.lock_draft()

    def test_forged_synthesis_is_rejected_after_valid_rehash(self) -> None:
        self.commit_one()
        self.rewrite_registered(
            "rounds.json",
            lambda value: value["data"]["rounds"][0]["synthesis"].append(
                "Forged rule."
            ),
        )
        with self.assertRaisesRegex(ProjectValidationError, "synthesis disagrees"):
            ProjectStore().load(self.root)

    def test_forged_derived_rules_are_rejected_after_valid_rehash(self) -> None:
        self.commit_one()
        self.rewrite_registered(
            "rounds.json",
            lambda value: value["data"]["rounds"][0].update(
                {"derived_rules": ["Forged rule."]}
            ),
        )
        with self.assertRaisesRegex(ProjectValidationError, "derived rules disagree"):
            ProjectStore().load(self.root)

    def test_missing_synthesis_is_rejected_after_valid_rehash(self) -> None:
        self.commit_one()
        self.rewrite_registered(
            "rounds.json",
            lambda value: value["data"]["rounds"][0].update({"synthesis": []}),
        )
        with self.assertRaisesRegex(ProjectValidationError, "synthesis disagrees"):
            ProjectStore().load(self.root)

    def test_wrong_synthesis_order_is_rejected(self) -> None:
        self.commit_two()

        def reverse_history(value) -> None:
            design_round = value["data"]["rounds"][0]
            design_round["synthesis"].reverse()
            design_round["derived_rules"].reverse()

        self.rewrite_registered("rounds.json", reverse_history)
        with self.assertRaisesRegex(ProjectValidationError, "synthesis disagrees"):
            ProjectStore().load(self.root)

    def test_low_level_raw_synthesis_writer_no_longer_exists(self) -> None:
        self.commit_one()
        manager = self.project.workspace.rounds
        self.assertFalse(hasattr(manager, "record_synthesis"))
        before = manager.get("round-1")
        manager._synchronize_decision_history("round-1")
        self.assertEqual(before, manager.get("round-1"))
        with self.assertRaises(TypeError):
            manager._synchronize_decision_history("round-1", "Forged rule.")

    def test_question_without_decision_is_trace_bound(self) -> None:
        self.project.start_session("question-only")
        draft = simple_draft()
        self.project.set_draft(
            DraftRound.create(
                draft_id=draft.draft_id,
                round_id=draft.round_id,
                topic=draft.topic,
                purpose=draft.purpose,
                questions=draft.questions,
                decisions=(),
            )
        )
        self.project.answer_draft("question-1", "B")
        self.project.lock_draft()
        original_rounds = (self.root / "rounds.json").read_bytes()
        original_manifest = (self.root / "manifest.json").read_bytes()
        transforms = (
            lambda question: question.update({"text": "Rewritten question?"}),
            lambda question: question["options"][0].update({"label": "Rewritten"}),
            lambda question: question["recommendation"].update(
                {"reason": "Rewritten recommendation."}
            ),
        )
        for transform in transforms:
            with self.subTest(transform=transform):
                self.rewrite_registered(
                    "rounds.json",
                    lambda value, transform=transform: transform(
                        value["data"]["rounds"][0]["questions"][0]
                    ),
                )
                with self.assertRaisesRegex(
                    ProjectValidationError, "registration TRACE|recommendation disagrees"
                ):
                    ProjectStore().load(self.root)
                (self.root / "rounds.json").write_bytes(original_rounds)
                (self.root / "manifest.json").write_bytes(original_manifest)

    def test_round_metadata_classification_is_enforced(self) -> None:
        self.commit_two()
        original_rounds = (self.root / "rounds.json").read_bytes()
        original_manifest = (self.root / "manifest.json").read_bytes()
        cases = (
            (
                lambda design_round: design_round.update({"purpose": "Forged purpose."}),
                "registration TRACE",
            ),
            (
                lambda design_round: design_round.update(
                    {"prerequisites": ["Forged prerequisite"]}
                ),
                "registration TRACE",
            ),
            (
                lambda design_round: design_round.update(
                    {"conflicts_detected": ["Forged conflict"]}
                ),
                "non-authoritative conflict",
            ),
        )
        for transform, message in cases:
            with self.subTest(message=message):
                self.rewrite_registered(
                    "rounds.json",
                    lambda value, transform=transform: transform(
                        value["data"]["rounds"][0]
                    ),
                )
                with self.assertRaisesRegex(ProjectValidationError, message):
                    ProjectStore().load(self.root)
                (self.root / "rounds.json").write_bytes(original_rounds)
                (self.root / "manifest.json").write_bytes(original_manifest)

    def test_valid_multi_decision_round_survives_unchanged(self) -> None:
        self.commit_two()
        loaded = PersistentProject.resume(self.root)
        design_round = loaded.workspace.rounds.get("round-two")
        expected = ("Use alpha.", "Use delta.")
        self.assertEqual(expected, design_round.synthesis)
        self.assertEqual(expected, design_round.derived_rules)
        self.assertEqual(
            ("Which first boundary?", "Which second boundary?"),
            tuple(question.text for question in design_round.questions),
        )
        self.assertEqual("Choose two ordered boundaries.", design_round.purpose)
        self.assertEqual(("Foundation accepted",), design_round.prerequisites)
        self.assertEqual((), design_round.conflicts_detected)


if __name__ == "__main__":
    import unittest

    unittest.main()
