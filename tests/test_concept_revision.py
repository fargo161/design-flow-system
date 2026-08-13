import unittest

from design_flow import (
    ConceptMaturity,
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
from test_semantic_integrity_lifecycle import add_decision


class ConceptRevisionTests(unittest.TestCase):
    def test_revision_refuses_untraced_source_decision(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="revision",
            name="Revision",
            description="Validate revision sources.",
            mode=DesignFlowMode.REPAIR,
            authority="Owner",
        )
        valid = add_decision(workspace, suffix="old", recommendation="A", answer="B")
        workspace.register_concept_from_decision(
            valid,
            concept_id="concept",
            canonical_name="CONCEPT",
            definition=valid.canonical_rule,
            maturity=ConceptMaturity.PROPOSED,
        )
        invalid = Decision(
            decision_id="invalid",
            canonical_rule="Invalid rule.",
            authoritative_value=("C",),
            status=DecisionStatus.SYNTHESIZED,
            scope="revision",
            source_round="missing",
            source_question="missing",
            provenance=DecisionProvenance(
                ("A",), "Advice", "C", ("C",), (), rule_source_value=("C",)
            ),
            trace_refs=["fake-trace"],
        )

        with self.assertRaisesRegex(ValueError, "does not exist"):
            workspace.concepts.revise(
                "concept",
                version="0.1.2",
                definition="Invalid revision.",
                source_decision=invalid,
            )

    def test_revision_refuses_synthesized_but_unregistered_source_decision(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="unregistered-revision",
            name="Unregistered Revision",
            description="Require ledger registration.",
            mode=DesignFlowMode.REPAIR,
            authority="Owner",
        )
        valid = add_decision(workspace, suffix="old", recommendation="A", answer="B")
        workspace.register_concept_from_decision(
            valid,
            concept_id="concept",
            canonical_name="CONCEPT",
            definition=valid.canonical_rule,
        )
        workspace.start_round(DesignRound("round-new", "New", "Choose replacement."))
        workspace.add_question(
            "round-new",
            Question(
                question_id="question-new",
                text="Which replacement?",
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=(
                    QuestionOption("A", "First"),
                    QuestionOption("B", "Second"),
                ),
                recommendation=Recommendation(("A",), "Advice"),
            ),
        )
        workspace.record_owner_answer("round-new", "question-new", "B")
        unregistered = workspace.synthesizer.synthesize(
            workspace.rounds.get("round-new"),
            "question-new",
            decision_id="decision-new",
            scope="revision",
            rule_mapping={"A": "First.", "B": "Second."},
        )

        with self.assertRaisesRegex(ValueError, "not registered"):
            workspace.concepts.revise(
                "concept",
                version="0.1.2",
                definition="Second.",
                source_decision=unregistered,
            )

    def test_status_and_maturity_are_independent_vocabularies(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="maturity",
            name="Maturity",
            description="Separate status from maturity.",
            mode=DesignFlowMode.DISCOVERY,
            authority="Owner",
        )
        decision = add_decision(workspace, suffix="one", recommendation="A", answer="B")
        concept = workspace.register_concept_from_decision(
            decision,
            concept_id="concept",
            canonical_name="CONCEPT",
            definition=decision.canonical_rule,
            maturity=ConceptMaturity.PROPOSED,
        )

        self.assertEqual("CURRENT", concept.status.value)
        self.assertEqual("PROPOSED", concept.maturity.value)
        self.assertNotEqual(type(concept.status), type(concept.maturity))


if __name__ == "__main__":
    unittest.main()
