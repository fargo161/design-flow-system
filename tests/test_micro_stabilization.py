import unittest
from dataclasses import FrozenInstanceError

from design_flow import (
    ConceptMaturity,
    ConceptStatus,
    ConflictRelation,
    DecisionStatus,
    DesignFlowMode,
    DesignFlowWorkspace,
    TraceAction,
)
from test_semantic_integrity_lifecycle import add_decision


def make_workspace(project_id: str = "micro") -> DesignFlowWorkspace:
    return DesignFlowWorkspace.create(
        project_id=project_id,
        name="Micro Stabilization",
        description="Exercise final integrity barriers.",
        mode=DesignFlowMode.REPAIR,
        authority="Owner",
    )


def assert_concept_is_immutable(test: unittest.TestCase, concept) -> None:
    assignments = (
        ("definition", "forged definition"),
        ("status", ConceptStatus.CURRENT),
        ("maturity", ConceptMaturity.STABLE),
        ("source_decisions", ("forged",)),
        ("trace_refs", ("forged",)),
    )
    for field, value in assignments:
        with test.subTest(field=field):
            with test.assertRaises((FrozenInstanceError, AttributeError)):
                setattr(concept, field, value)
    with test.assertRaises(TypeError):
        concept.provenance["forged"] = True
    with test.assertRaises(TypeError):
        concept.provenance["current_source"]["source_decision"] = "forged"


class ConceptImmutabilityTests(unittest.TestCase):
    def test_current_affected_and_historical_accessors_expose_immutable_records(self) -> None:
        workspace = make_workspace("concept-immutability")
        old = add_decision(workspace, suffix="old", recommendation="A", answer="B")
        owns = ["original ownership"]
        current = workspace.register_concept_from_decision(
            old,
            concept_id="concept",
            canonical_name="CONCEPT",
            definition=old.canonical_rule,
            owns=owns,
        )
        owns.append("forged ownership")
        assert_concept_is_immutable(self, current)
        assert_concept_is_immutable(self, workspace.concepts.get("concept"))
        assert_concept_is_immutable(self, workspace.concepts.concepts[0])
        self.assertEqual(("original ownership",), current.owns)
        self.assertEqual(old.canonical_rule, workspace.concepts.get("concept").definition)

        new = add_decision(workspace, suffix="new", recommendation="A", answer="C")
        workspace.ledger.supersede("decision-old", "decision-new", notes="Replace old.")
        affected = workspace.concepts.affected[0]
        assert_concept_is_immutable(self, affected)
        self.assertEqual(ConceptStatus.UNRESOLVED, workspace.concepts.get("concept").status)

        revised = workspace.concepts.revise(
            "concept",
            version="0.1.1+revision.1",
            definition=new.canonical_rule,
            source_decision=new,
        )
        historical = workspace.concepts.history[0]
        assert_concept_is_immutable(self, historical)
        assert_concept_is_immutable(self, revised)
        self.assertEqual(old.canonical_rule, historical.definition)
        self.assertEqual(new.canonical_rule, workspace.concepts.get("concept").definition)
        self.assertEqual(("concept@0.1.1",), revised.supersedes)


class TraceImmutabilityTests(unittest.TestCase):
    def test_details_are_deeply_immutable_and_external_aliases_are_severed(self) -> None:
        workspace = make_workspace("trace-immutability")
        payload = {"values": ["B"], "nested": {"rule": "original"}}
        trace_id = workspace.trace.record(
            TraceAction.GENERATE_DOCUMENT,
            "document",
            "document",
            payload=payload,
            canonical_rule="original",
        )
        payload["values"].append("A")
        payload["nested"]["rule"] = "forged"

        record = workspace.trace.get(trace_id)
        self.assertEqual(("B",), record.details["payload"]["values"])
        self.assertEqual("original", record.details["payload"]["nested"]["rule"])
        with self.assertRaises(TypeError):
            record.details["canonical_rule"] = "forged"
        with self.assertRaises(TypeError):
            record.details["payload"]["nested"]["rule"] = "forged"
        with self.assertRaises(FrozenInstanceError):
            record.entity_id = "forged"

        retrieved = (
            workspace.trace.records[-1],
            workspace.trace.for_entity("document")[0],
            workspace.trace.get(trace_id),
        )
        for item in retrieved:
            with self.assertRaises(TypeError):
                item.details["payload"]["values"] = ("A",)
        self.assertEqual(("B",), workspace.trace.get(trace_id).details["payload"]["values"])


class SupersessionSafetyTests(unittest.TestCase):
    def test_self_supersession_is_rejected_without_state_change(self) -> None:
        workspace = make_workspace("self-supersession")
        decision = add_decision(workspace, suffix="a", recommendation="B", answer="A")
        with self.assertRaisesRegex(ValueError, "cannot supersede itself"):
            workspace.ledger.supersede("decision-a", "decision-a", notes="Invalid.")
        self.assertEqual(DecisionStatus.SYNTHESIZED, decision.status)
        self.assertEqual((), workspace.ledger.relationships)

    def test_superseded_decision_cannot_be_used_as_replacement(self) -> None:
        workspace = make_workspace("ineligible-replacement")
        a = add_decision(workspace, suffix="a", recommendation="B", answer="A")
        add_decision(workspace, suffix="b", recommendation="A", answer="B")
        add_decision(workspace, suffix="c", recommendation="A", answer="C")
        workspace.ledger.supersede("decision-a", "decision-b", notes="A to B.")
        with self.assertRaisesRegex(ValueError, "not current/eligible"):
            workspace.ledger.supersede("decision-c", "decision-a", notes="Invalid.")
        self.assertEqual(DecisionStatus.SUPERSEDED, a.status)
        self.assertEqual(DecisionStatus.SYNTHESIZED, workspace.ledger.get("decision-c").status)

    def test_preexisting_supersession_relation_is_not_duplicated(self) -> None:
        workspace = make_workspace("duplicate-relation")
        a = add_decision(workspace, suffix="a", recommendation="B", answer="A")
        b = add_decision(workspace, suffix="b", recommendation="A", answer="B")
        workspace.ledger.record_relationship(
            "decision-a",
            "decision-b",
            ConflictRelation.SUPERSEDES,
            "Pre-existing relation.",
        )

        with self.assertRaisesRegex(ValueError, "already exists"):
            workspace.ledger.supersede("decision-a", "decision-b", notes="Duplicate.")
        self.assertEqual(DecisionStatus.SYNTHESIZED, a.status)
        self.assertEqual(DecisionStatus.SYNTHESIZED, b.status)
        self.assertEqual(1, len(workspace.ledger.relationships))

    def test_cycle_attempt_is_rejected(self) -> None:
        workspace = make_workspace("cycle")
        add_decision(workspace, suffix="a", recommendation="B", answer="A")
        add_decision(workspace, suffix="b", recommendation="A", answer="B")
        add_decision(workspace, suffix="c", recommendation="A", answer="C")
        workspace.ledger.supersede("decision-a", "decision-b", notes="A to B.")
        workspace.ledger.supersede("decision-b", "decision-c", notes="B to C.")

        # Restore the historical candidate only to reach the explicit ancestry guard;
        # ordinary use is already rejected by the ineligible-replacement guard.
        workspace.ledger.get("decision-a").status = DecisionStatus.SYNTHESIZED
        with self.assertRaisesRegex(ValueError, "create a cycle"):
            workspace.ledger.supersede("decision-c", "decision-a", notes="C to A.")
        self.assertEqual(DecisionStatus.SYNTHESIZED, workspace.ledger.get("decision-c").status)

    def test_valid_linear_chain_preserves_history_and_concept_quarantine(self) -> None:
        workspace = make_workspace("linear-chain")
        a = add_decision(workspace, suffix="a", recommendation="B", answer="A")
        workspace.register_concept_from_decision(
            a,
            concept_id="concept",
            canonical_name="CONCEPT",
            definition=a.canonical_rule,
        )
        b = add_decision(workspace, suffix="b", recommendation="A", answer="B")
        c = add_decision(workspace, suffix="c", recommendation="A", answer="C")

        workspace.ledger.supersede("decision-a", "decision-b", notes="A to B.")
        workspace.concepts.revise(
            "concept",
            version="0.1.1+revision.1",
            definition=b.canonical_rule,
            source_decision=b,
        )
        workspace.ledger.supersede("decision-b", "decision-c", notes="B to C.")

        self.assertEqual(DecisionStatus.SUPERSEDED, a.status)
        self.assertEqual(DecisionStatus.SUPERSEDED, b.status)
        self.assertEqual(DecisionStatus.SYNTHESIZED, c.status)
        self.assertEqual(
            ("decision-a", "decision-b", "decision-c"),
            tuple(item.decision_id for item in workspace.ledger.decisions),
        )
        state = workspace.state_compiler.compile(workspace.project, workspace.ledger)
        self.assertEqual(("decision-c",), tuple(item.decision_id for item in state.decisions))
        self.assertEqual((), workspace.concepts.concepts)
        self.assertEqual(("concept",), tuple(item.concept_id for item in workspace.concepts.affected))
        self.assertEqual(("decision-a", "decision-b"), c.supersedes)
        first = workspace.render_application_document()
        second = workspace.render_application_document()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
