import unittest

from design_flow import (
    ConceptMaturity,
    ConceptStatus,
    DecisionStatus,
    DesignFlowMode,
    DesignFlowWorkspace,
    DesignRound,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
)


def add_decision(
    workspace: DesignFlowWorkspace,
    *,
    suffix: str,
    recommendation: str,
    answer: str,
):
    round_id = f"round-{suffix}"
    question_id = f"question-{suffix}"
    workspace.start_round(DesignRound(round_id, "Target Model", "Select the target model."))
    workspace.add_question(
        round_id,
        Question(
            question_id=question_id,
            text="Which target model applies?",
            question_type=QuestionType.MULTIPLE_CHOICE,
            options=(
                QuestionOption("A", "Actor identity"),
                QuestionOption("B", "Fixed position"),
                QuestionOption("C", "Current actor position"),
            ),
            recommendation=Recommendation((recommendation,), f"{recommendation} is advised."),
        ),
    )
    workspace.record_owner_answer(round_id, question_id, answer)
    return workspace.synthesize_decision(
        round_id,
        question_id,
        decision_id=f"decision-{suffix}",
        scope="target-model",
        rule_mapping={
            "A": "Movement targets actor identity.",
            "B": "Movement targets a fixed position.",
            "C": "Movement follows the actor's current position.",
        },
    )


class SemanticIntegrityLifecycleTests(unittest.TestCase):
    def test_supersession_revision_and_recompile_have_no_stale_current_semantics(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="lifecycle",
            name="Lifecycle",
            description="Exercise the complete semantic lifecycle.",
            mode=DesignFlowMode.REPAIR,
            authority="Owner answers are authoritative.",
        )

        old = add_decision(
            workspace,
            suffix="old",
            recommendation="A",
            answer="B",
        )
        concept_v1 = workspace.register_concept_from_decision(
            old,
            concept_id="movement.target-model",
            canonical_name="MOVEMENT_TARGET_MODEL",
            definition=old.canonical_rule,
            maturity=ConceptMaturity.DEFINED,
            boundaries=("Only target identity is in scope.",),
        )
        initial = workspace.render_application_document()

        self.assertEqual(("A",), old.provenance.recommendation_was)
        self.assertEqual(("B",), old.authoritative_value)
        self.assertIn("Movement targets a fixed position.", initial)
        self.assertEqual("decision-old", concept_v1.provenance["current_source"]["source_decision"])

        new = add_decision(
            workspace,
            suffix="new",
            recommendation="A",
            answer="C",
        )
        workspace.ledger.supersede(
            "decision-old",
            "decision-new",
            notes="The owner replaced the fixed position with current actor position.",
        )

        self.assertEqual(DecisionStatus.SUPERSEDED, old.status)
        self.assertEqual(("decision-new",), tuple(d.decision_id for d in workspace.state_compiler.compile(workspace.project, workspace.ledger).decisions))
        self.assertEqual((), workspace.concepts.concepts)
        self.assertEqual(("movement.target-model",), tuple(c.concept_id for c in workspace.concepts.affected))
        self.assertEqual(ConceptStatus.UNRESOLVED, workspace.concepts.affected[0].status)

        affected_document = workspace.render_application_document()
        current_section = affected_document.split("## Current Decisions", 1)[0]
        self.assertNotIn("### MOVEMENT_TARGET_MODEL", current_section)
        self.assertIn("movement.target-model@0.1.1", affected_document)

        concept_v2 = workspace.concepts.revise(
            "movement.target-model",
            version="0.1.2",
            definition=new.canonical_rule,
            source_decision=new,
            maturity=ConceptMaturity.DEFINED,
        )
        second = workspace.render_application_document()
        third = workspace.render_application_document()

        self.assertEqual(ConceptStatus.CURRENT, concept_v2.status)
        self.assertEqual(ConceptMaturity.DEFINED, concept_v2.maturity)
        self.assertEqual("decision-new", concept_v2.provenance["current_source"]["source_decision"])
        self.assertEqual("round-new", concept_v2.provenance["current_source"]["source_round"])
        self.assertEqual(("C",), concept_v2.provenance["current_source"]["owner_answer"])
        self.assertEqual(("A",), concept_v2.provenance["current_source"]["recommendation_was"])
        self.assertEqual("decision-old", concept_v2.provenance["original_source"]["source_decision"])
        self.assertEqual(("movement.target-model@0.1.1",), concept_v2.supersedes)
        self.assertEqual(ConceptStatus.SUPERSEDED, workspace.concepts.history[0].status)

        current_concepts = second.split("## Current Decisions", 1)[0]
        current_decisions = second.split("## Current Decisions", 1)[1].split("## Unresolved Register", 1)[0]
        historical = second.split("## Superseded / Historical State", 1)[1]
        self.assertIn("Movement follows the actor's current position.", current_concepts)
        self.assertNotIn("Movement targets a fixed position.", current_concepts)
        self.assertIn("decision-new", current_decisions)
        self.assertNotIn("### decision-old", current_decisions)
        self.assertIn("decision-old", historical)
        self.assertIn("movement.target-model@0.1.1", historical)
        self.assertEqual(second, third)

    def test_deprecate_and_explicit_unresolved_paths_remove_settled_current_state(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="resolution-paths",
            name="Resolution Paths",
            description="Exercise conservative concept resolution.",
            mode=DesignFlowMode.REPAIR,
            authority="Owner",
        )
        decision = add_decision(workspace, suffix="one", recommendation="A", answer="B")
        workspace.register_concept_from_decision(
            decision,
            concept_id="concept.one",
            canonical_name="CONCEPT_ONE",
            definition=decision.canonical_rule,
        )
        unresolved = workspace.concepts.mark_unresolved(
            "concept.one", reason="Owner resolution is required."
        )
        self.assertEqual(ConceptStatus.UNRESOLVED, unresolved.status)
        self.assertEqual((), workspace.concepts.concepts)

        deprecated = workspace.concepts.deprecate(
            "concept.one", reason="The concept is no longer operative."
        )
        self.assertEqual(ConceptStatus.DEPRECATED, deprecated.status)
        self.assertEqual(ConceptMaturity.DEPRECATED, deprecated.maturity)
        self.assertEqual((), workspace.concepts.affected)
        self.assertIn(deprecated, workspace.concepts.history)

    def test_binding_is_explicitly_non_consequence_bearing_scaffolding(self) -> None:
        workspace = DesignFlowWorkspace.create(
            project_id="binding",
            name="Binding",
            description="Describe the scaffold honestly.",
            mode=DesignFlowMode.DISCOVERY,
            authority="Owner",
        )
        decision = add_decision(workspace, suffix="one", recommendation="A", answer="B")
        workspace.register_concept_from_decision(
            decision,
            concept_id="concept.binding",
            canonical_name="CONCEPT_BINDING",
            definition=decision.canonical_rule,
        )
        bindings = workspace.document_renderer.bindings_for(workspace.concepts)
        markdown = workspace.render_application_document()

        self.assertEqual("concept:concept.binding", bindings[0].section_key)
        self.assertIn("not consequence-bearing", markdown)
        self.assertNotIn("Application binding: `IMPLEMENTED`", markdown)


if __name__ == "__main__":
    unittest.main()
