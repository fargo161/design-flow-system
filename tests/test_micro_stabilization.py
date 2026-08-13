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


def assert_decision_is_immutable(test: unittest.TestCase, decision) -> None:
    assignments = (
        ("status", DecisionStatus.SUPERSEDED),
        ("canonical_rule", "forged rule"),
        ("authoritative_value", ("A",)),
        ("supersedes", ("forged",)),
        ("trace_refs", ("forged",)),
    )
    for field, value in assignments:
        with test.subTest(field=field):
            with test.assertRaises((FrozenInstanceError, AttributeError)):
                setattr(decision, field, value)


class DecisionImmutabilityTests(unittest.TestCase):
    def test_ledger_and_current_state_accessors_expose_immutable_snapshots(self) -> None:
        workspace = make_workspace("decision-immutability")
        registered = add_decision(
            workspace, suffix="current", recommendation="A", answer="B"
        )
        state = workspace.state_compiler.compile(workspace.project, workspace.ledger)
        trace_count = len(workspace.trace)

        for decision in (
            registered,
            workspace.ledger.get("decision-current"),
            workspace.ledger.decisions[0],
            state.decisions[0],
        ):
            assert_decision_is_immutable(self, decision)

        stored = workspace.ledger.get("decision-current")
        self.assertEqual(DecisionStatus.SYNTHESIZED, stored.status)
        self.assertEqual(("B",), stored.authoritative_value)
        self.assertEqual((), stored.supersedes)
        self.assertEqual(trace_count, len(workspace.trace))
        self.assertFalse(
            any(record.action is TraceAction.SUPERSEDE for record in workspace.trace.records)
        )
        current = workspace.state_compiler.compile(workspace.project, workspace.ledger)
        self.assertEqual(("decision-current",), tuple(item.decision_id for item in current.decisions))


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

    def test_unsupported_mutable_payloads_are_rejected_without_trace_append(self) -> None:
        class MutablePayload:
            def __init__(self) -> None:
                self.value = "mutable"

        workspace = make_workspace("trace-admission-rejection")
        initial_count = len(workspace.trace)
        with self.assertRaisesRegex(TypeError, "Unsupported semantic value type"):
            workspace.trace.record(
                TraceAction.GENERATE_DOCUMENT,
                "document",
                "custom-payload",
                payload=MutablePayload(),
            )
        with self.assertRaisesRegex(TypeError, "Unsupported semantic value type"):
            workspace.trace.record(
                TraceAction.GENERATE_DOCUMENT,
                "document",
                "nested-custom-payload",
                payload={"nested": MutablePayload()},
            )
        cyclic: list[object] = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(TypeError, "Cyclic semantic containers"):
            workspace.trace.record(
                TraceAction.GENERATE_DOCUMENT,
                "document",
                "cyclic-payload",
                payload=cyclic,
            )
        self.assertEqual(initial_count, len(workspace.trace))

    def test_safe_trace_payload_families_are_normalized_and_accepted(self) -> None:
        workspace = make_workspace("trace-admission-safe")
        trace_id = workspace.trace.record(
            TraceAction.GENERATE_DOCUMENT,
            "document",
            "safe-payload",
            text="value",
            enabled=True,
            count=3,
            optional=None,
            sequence=["A", "B"],
            mapping={"answer": ["B"]},
            choices={"A", "B"},
            status=DecisionStatus.SYNTHESIZED,
        )

        details = workspace.trace.get(trace_id).details
        self.assertEqual(("A", "B"), details["sequence"])
        self.assertEqual(("B",), details["mapping"]["answer"])
        self.assertEqual(frozenset({"A", "B"}), details["choices"])
        self.assertEqual("SYNTHESIZED", details["status"])


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
        self.assertEqual(
            DecisionStatus.SUPERSEDED,
            workspace.ledger.get("decision-a").status,
        )
        self.assertEqual(DecisionStatus.SYNTHESIZED, workspace.ledger.get("decision-c").status)

    def test_supersedes_is_reserved_but_other_relationships_and_guarded_path_work(self) -> None:
        workspace = make_workspace("guarded-relation")
        a = add_decision(workspace, suffix="a", recommendation="B", answer="A")
        b = add_decision(workspace, suffix="b", recommendation="A", answer="B")
        trace_count = len(workspace.trace)

        with self.assertRaisesRegex(ValueError, "must be created through supersede"):
            workspace.ledger.record_relationship(
                "decision-a",
                "decision-b",
                ConflictRelation.SUPERSEDES,
                "Bypass attempt.",
            )
        self.assertEqual(DecisionStatus.SYNTHESIZED, a.status)
        self.assertEqual(DecisionStatus.SYNTHESIZED, b.status)
        self.assertEqual((), workspace.ledger.relationships)
        self.assertEqual(trace_count, len(workspace.trace))

        conflict = workspace.ledger.record_relationship(
            "decision-a",
            "decision-b",
            ConflictRelation.POTENTIAL_CONFLICT,
            "Review required.",
        )
        self.assertEqual(ConflictRelation.POTENTIAL_CONFLICT, conflict.relation)

        workspace.ledger.supersede("decision-a", "decision-b", notes="Guarded path.")
        self.assertEqual(
            DecisionStatus.SUPERSEDED,
            workspace.ledger.get("decision-a").status,
        )
        self.assertEqual(("decision-a",), workspace.ledger.get("decision-b").supersedes)
        self.assertEqual(
            (ConflictRelation.POTENTIAL_CONFLICT, ConflictRelation.SUPERSEDES),
            tuple(item.relation for item in workspace.ledger.relationships),
        )
        self.assertEqual(trace_count + 1, len(workspace.trace))
        self.assertEqual(TraceAction.SUPERSEDE, workspace.trace.records[-1].action)
        with self.assertRaisesRegex(ValueError, "current synthesized"):
            workspace.register_concept_from_decision(
                a,
                concept_id="stale-source",
                canonical_name="STALE_SOURCE",
                definition=a.canonical_rule,
            )
        relationship_count = len(workspace.ledger.relationships)
        with self.assertRaisesRegex(ValueError, "already superseded"):
            workspace.ledger.supersede("decision-a", "decision-b", notes="Duplicate.")
        self.assertEqual(relationship_count, len(workspace.ledger.relationships))

    def test_cycle_attempt_is_rejected(self) -> None:
        workspace = make_workspace("cycle")
        add_decision(workspace, suffix="a", recommendation="B", answer="A")
        add_decision(workspace, suffix="b", recommendation="A", answer="B")
        add_decision(workspace, suffix="c", recommendation="A", answer="C")
        workspace.ledger.supersede("decision-a", "decision-b", notes="A to B.")
        workspace.ledger.supersede("decision-b", "decision-c", notes="B to C.")

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

        self.assertEqual(
            DecisionStatus.SUPERSEDED,
            workspace.ledger.get("decision-a").status,
        )
        self.assertEqual(
            DecisionStatus.SUPERSEDED,
            workspace.ledger.get("decision-b").status,
        )
        self.assertEqual(
            DecisionStatus.SYNTHESIZED,
            workspace.ledger.get("decision-c").status,
        )
        self.assertEqual(
            ("decision-a", "decision-b", "decision-c"),
            tuple(item.decision_id for item in workspace.ledger.decisions),
        )
        state = workspace.state_compiler.compile(workspace.project, workspace.ledger)
        self.assertEqual(("decision-c",), tuple(item.decision_id for item in state.decisions))
        self.assertEqual((), workspace.concepts.concepts)
        self.assertEqual(("concept",), tuple(item.concept_id for item in workspace.concepts.affected))
        self.assertEqual(
            ("decision-a", "decision-b"),
            workspace.ledger.get("decision-c").supersedes,
        )
        first = workspace.render_application_document()
        second = workspace.render_application_document()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
