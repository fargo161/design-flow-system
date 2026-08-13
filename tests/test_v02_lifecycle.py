from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from design_flow import (
    CommandRunner,
    ConceptStatus,
    DesignFlowMode,
    DraftConceptAction,
    DraftConceptPlan,
    DraftDecisionPlan,
    DraftQuestion,
    DraftRound,
    LLMUnavailableError,
    PersistentProject,
    QuestionOption,
    QuestionType,
    Recommendation,
    compile_context_handoff,
    request_draft,
)


def question(question_id: str, text: str, keys: tuple[str, ...] = ("A", "B")) -> DraftQuestion:
    return DraftQuestion(
        question_id,
        text,
        QuestionType.MULTIPLE_CHOICE,
        tuple(QuestionOption(key, f"Choice {key}") for key in keys),
        Recommendation((keys[0],), f"Choice {keys[0]} is the smallest first step."),
    )


class FullLifecycleTest(unittest.TestCase):
    def test_three_round_resume_qualified_supersession_and_compilers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "acceptance-project"
            project = PersistentProject.create(
                root,
                project_id="acceptance-project",
                name="Acceptance Project",
                description="Three-round durable proof.",
                mode=DesignFlowMode.DISCOVERY,
                authority="Only explicit owner locks create authority.",
            )

            project.start_session("session-intake")
            first = DraftRound.create(
                draft_id="draft-round-1",
                round_id="round-1",
                topic="Identity",
                purpose="Choose the operative identity.",
                questions=(question("question-identity", "Which identity?"),),
                decisions=(
                    DraftDecisionPlan.create(
                        question_id="question-identity",
                        decision_id="decision-identity-v1",
                        scope="identity",
                        rule_mapping={"A": "Use actor identity.", "B": "Use location identity."},
                        concept=DraftConceptPlan(
                            DraftConceptAction.REGISTER,
                            "identity.target",
                            "IDENTITY_TARGET",
                            "Use location identity.",
                            owns=("operative target identity",),
                        ),
                    ),
                ),
            )
            project.set_draft(first)
            project.answer_draft("question-identity", "B")
            trace_before_preview = tuple(project.workspace.trace.records)
            preview = project.preview_draft()
            self.assertEqual(("Use location identity.",), preview.derived_rules)
            self.assertEqual(trace_before_preview, project.workspace.trace.records)
            project.lock_draft()
            project.end_session()

            project = PersistentProject.resume(root)
            self.assertEqual("acceptance-project", project.workspace.project.project_id)
            self.assertEqual("decision-identity-v1", project.workspace.ledger.decisions[0].decision_id)
            project.start_session("session-qualified")
            second = DraftRound.create(
                draft_id="draft-round-2",
                round_id="round-2",
                topic="Qualified policy",
                purpose="Preserve owner qualification as unresolved authority.",
                questions=(
                    question("question-policy", "Which policies?", ("A", "B", "C")),
                ),
                decisions=(
                    DraftDecisionPlan.create(
                        question_id="question-policy",
                        decision_id="decision-policy-qualified",
                        scope="policy",
                        rule_mapping={
                            ("A", "C"): "Use A and C only under the owner-stated context."
                        },
                    ),
                ),
            )
            project.set_draft(second)
            project.answer_draft("question-policy", "A + C depending on context")
            project.lock_draft()
            qualified = project.workspace.ledger.get("decision-policy-qualified")
            self.assertEqual(("A", "C"), qualified.authoritative_value)
            self.assertEqual(("depending on context",), qualified.provenance.owner_qualifiers)
            self.assertTrue(qualified.unresolved_consequences)
            project.end_session()

            project = PersistentProject.resume(root)
            project.start_session("session-correction")
            third = DraftRound.create(
                draft_id="draft-round-3",
                round_id="round-3",
                topic="Identity correction",
                purpose="Correct history by explicit supersession.",
                questions=(question("question-identity-v2", "Which identity now?"),),
                decisions=(
                    DraftDecisionPlan.create(
                        question_id="question-identity-v2",
                        decision_id="decision-identity-v2",
                        scope="identity",
                        rule_mapping={"A": "Use stable actor identity.", "B": "Use location identity."},
                        supersedes_decision="decision-identity-v1",
                        supersession_notes="Owner explicitly corrected the identity boundary.",
                        concept=DraftConceptPlan(
                            DraftConceptAction.REVISE,
                            "identity.target",
                            "IDENTITY_TARGET",
                            "Use stable actor identity.",
                            version="0.2.0",
                            owns=("operative target identity",),
                        ),
                    ),
                ),
            )
            project.set_draft(third)
            project.answer_draft("question-identity-v2", "A")
            project.lock_draft()
            self.assertEqual(
                ConceptStatus.CURRENT,
                project.workspace.concepts.get("identity.target").status,
            )
            self.assertEqual(
                ("decision-identity-v1",),
                project.workspace.ledger.get("decision-identity-v2").supersedes,
            )
            generated = project.compile_artifacts()
            self.assertEqual(2, len(generated))
            project.end_session()
            project.compile_artifacts()

            final = PersistentProject.resume(root)
            self.assertEqual(3, len(final.workspace.rounds.rounds))
            self.assertEqual(3, len(final.workspace.ledger.decisions))
            self.assertGreater(len(final.workspace.trace.records), 20)
            self.assertEqual("CURRENT", final.artifact_status("generated/context_handoff.md"))
            handoff = compile_context_handoff(final.workspace, final.sessions)
            self.assertIn("decision-identity-v1` → `decision-identity-v2", handoff)
            self.assertIn("depending on context", handoff)
            self.assertIn("IDENTITY_TARGET", handoff)
            self.assertEqual(
                "acceptance-project",
                final.sessions[0].project_id,
            )

    def test_runner_and_no_llm_are_deterministically_usable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = PersistentProject.create(
                Path(temporary) / "manual",
                project_id="manual",
                name="Manual",
                description="No provider required.",
                mode=DesignFlowMode.REFINEMENT,
                authority="Owner",
            )
            project.start_session("manual-session")
            runner = CommandRunner(project)
            self.assertIn("Project: Manual", runner.execute("STATE"))
            self.assertIn("ANSWER", runner.execute("HELP"))
            with self.assertRaises(LLMUnavailableError):
                request_draft(None, compile_context_handoff(project.workspace, project.sessions))
            self.assertIn("generation", runner.execute("SAVE"))
            self.assertIn("Ended session", runner.execute("END SESSION"))


if __name__ == "__main__":
    unittest.main()
