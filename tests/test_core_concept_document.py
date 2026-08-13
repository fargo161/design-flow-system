import unittest

from design_flow.demo import build_demo


class CoreConceptDocumentTests(unittest.TestCase):
    def test_concept_preserves_source_decision_and_boundary(self) -> None:
        workspace, _ = build_demo()
        concept = workspace.concepts.get("movement.target_identity")

        self.assertEqual(("decision.movement-target-identity",), concept.source_decisions)
        self.assertEqual(("Only relational movement is in scope.",), concept.boundaries)
        current_source = concept.provenance["current_source"]
        self.assertEqual(["B"], current_source["owner_answer"])
        self.assertEqual(["A"], current_source["recommendation_was"])
        self.assertTrue(concept.trace_refs)

    def test_living_document_renders_authority_status_provenance_and_trace(self) -> None:
        _, markdown = build_demo()

        self.assertIn("## Document Identity", markdown)
        self.assertIn("Authority: The project owner is the design authority.", markdown)
        self.assertIn("### MOVEMENT_TARGET_IDENTITY", markdown)
        self.assertIn("Status: `CURRENT`", markdown)
        self.assertIn("Authoritative owner value: `B`", markdown)
        self.assertIn("Historical recommendation: `A`", markdown)
        self.assertIn("## Unresolved Register", markdown)
        self.assertIn("## Superseded / Historical State", markdown)
        self.assertIn("## TRACE / Recent Changes", markdown)
        self.assertIn("`REGISTER_DECISION`", markdown)
        self.assertIn("`GENERATE_DOCUMENT`", markdown)


if __name__ == "__main__":
    unittest.main()
