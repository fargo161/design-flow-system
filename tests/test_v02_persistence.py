from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from design_flow import (
    DesignFlowMode,
    DraftConceptAction,
    DraftConceptPlan,
    DraftDecisionPlan,
    DraftQuestion,
    DraftRound,
    PersistentProject,
    ProjectStore,
    ProjectValidationError,
    QuestionOption,
    QuestionType,
    Recommendation,
    SourceReference,
    TraceAction,
)
from design_flow.persistence import canonical_json_bytes


def simple_draft(
    *,
    draft_id: str = "draft-1",
    round_id: str = "round-1",
    decision_id: str = "decision-1",
    rules: dict[str | tuple[str, ...], str] | None = None,
    with_concept: bool = False,
) -> DraftRound:
    return DraftRound.create(
        draft_id=draft_id,
        round_id=round_id,
        topic="Boundary",
        purpose="Choose one boundary.",
        questions=(
            DraftQuestion(
                "question-1",
                "Which boundary?",
                QuestionType.MULTIPLE_CHOICE,
                (QuestionOption("A", "Alpha"), QuestionOption("B", "Beta")),
                Recommendation(("A",), "Alpha is the smaller initial surface."),
            ),
        ),
        decisions=(
            DraftDecisionPlan.create(
                question_id="question-1",
                decision_id=decision_id,
                scope="boundary",
                rule_mapping=rules or {"A": "Use alpha.", "B": "Use beta."},
                concept=(
                    DraftConceptPlan(
                        DraftConceptAction.REGISTER,
                        "concept-1",
                        "BOUNDARY_CONCEPT",
                        "Use beta.",
                    )
                    if with_concept
                    else None
                ),
            ),
        ),
    )


class ProjectCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.project = PersistentProject.create(
            self.root,
            project_id="project-stable",
            name="Stable Project",
            description="A durable test project.",
            mode=DesignFlowMode.DISCOVERY,
            authority="The owner is authoritative.",
            unresolved_areas=("Initial seam",),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def commit_one(self) -> None:
        self.project.start_session("session-1")
        self.project.set_draft(simple_draft())
        self.project.answer_draft("question-1", "B")
        self.project.lock_draft()

    def rewrite_registered(self, relative: str, transform) -> None:
        path = self.root / relative
        value = json.loads(path.read_text(encoding="utf-8"))
        transform(value)
        data = canonical_json_bytes(value)
        path.write_bytes(data)

        manifest_path = self.root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in (*manifest["authoritative_files"], *manifest["operational_files"]):
            if entry["path"] == relative:
                entry["content_hash"] = hashlib.sha256(data).hexdigest()
        for entry in manifest["authoritative_files"]:
            if entry["path"] == "manifest.json":
                entry["content_hash"] = ""
        projected = canonical_json_bytes(manifest)
        self_hash = hashlib.sha256(projected).hexdigest()
        for entry in manifest["authoritative_files"]:
            if entry["path"] == "manifest.json":
                entry["content_hash"] = self_hash
        manifest_path.write_bytes(canonical_json_bytes(manifest))

    def test_round_trip_ids_trace_continuity_and_project_metadata(self) -> None:
        self.commit_one()
        before_ids = tuple(item.trace_id for item in self.project.workspace.trace.records)
        resumed = PersistentProject.resume(self.root)
        self.assertEqual("project-stable", resumed.workspace.project.project_id)
        self.assertEqual(["Initial seam"], resumed.workspace.project.unresolved_areas)
        self.assertEqual("round-1", resumed.workspace.rounds.rounds[0].round_id)
        self.assertEqual("decision-1", resumed.workspace.ledger.decisions[0].decision_id)
        self.assertEqual(before_ids, tuple(item.trace_id for item in resumed.workspace.trace.records))
        next_id = resumed.workspace.trace.record(TraceAction.GENERATE_DOCUMENT, "test", "next")
        self.assertNotIn(next_id, before_ids)

    def test_draft_persists_without_authority_and_resume_keeps_lineage(self) -> None:
        self.project.start_session("session-draft")
        self.project.set_draft(simple_draft())
        self.project.answer_draft("question-1", "A")
        self.project.compile_artifacts()
        self.assertNotIn(
            "Use alpha.",
            (self.root / "generated/living_application.md").read_text(encoding="utf-8"),
        )
        resumed = PersistentProject.resume(self.root)
        self.assertEqual("project-stable", resumed.workspace.project.project_id)
        self.assertEqual((), resumed.workspace.rounds.rounds)
        self.assertEqual((), resumed.workspace.ledger.decisions)
        self.assertEqual("A", resumed.draft.answers["question-1"])
        self.assertEqual("session-draft", resumed.sessions[-1].session_id)

    def test_failed_lock_preserves_draft_and_no_partial_authority(self) -> None:
        self.project.start_session("session-failed")
        self.project.set_draft(simple_draft(rules={"A": "Only alpha exists."}))
        self.project.answer_draft("question-1", "B")
        with self.assertRaisesRegex(ProjectValidationError, "draft preserved"):
            self.project.lock_draft()
        self.assertIsNotNone(self.project.draft)
        self.assertEqual((), self.project.workspace.rounds.rounds)
        resumed = PersistentProject.resume(self.root)
        self.assertIsNotNone(resumed.draft)
        self.assertEqual((), resumed.workspace.ledger.decisions)

    def test_source_unavailable_does_not_invalidate_authority(self) -> None:
        self.project.add_source(
            SourceReference("source-1", "Optional local evidence", local_path="sources/missing.md")
        )
        self.assertEqual("UNAVAILABLE", self.project.source_status("source-1"))
        self.assertEqual("project-stable", PersistentProject.resume(self.root).workspace.project.project_id)

    def test_unknown_field_is_rejected_after_valid_rehash(self) -> None:
        self.rewrite_registered("rounds.json", lambda value: value["data"].update({"surprise": 1}))
        with self.assertRaisesRegex(ProjectValidationError, "unknown fields"):
            ProjectStore().load(self.root)

    def test_unsupported_format_missing_file_and_hash_mismatch_are_rejected(self) -> None:
        manifest_path = self.root / "manifest.json"
        original = manifest_path.read_bytes()
        manifest = json.loads(original)
        manifest["project_format_version"] = "9.9.9"
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(ProjectValidationError, "Unsupported project_format_version"):
            ProjectStore().load(self.root)
        manifest_path.write_bytes(original)

        rounds_path = self.root / "rounds.json"
        rounds = rounds_path.read_bytes()
        rounds_path.unlink()
        with self.assertRaisesRegex(ProjectValidationError, "Missing registered file"):
            ProjectStore().load(self.root)
        rounds_path.write_bytes(rounds)

        rounds_path.write_bytes(rounds + b" ")
        with self.assertRaises(ProjectValidationError):
            ProjectStore().load(self.root)

    def test_mixed_generation_and_invalid_cross_reference_are_rejected(self) -> None:
        self.commit_one()
        manifest_path = self.root / "manifest.json"
        original = manifest_path.read_bytes()
        manifest = json.loads(original)
        manifest["authoritative_files"][1]["save_generation"] -= 1
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        with self.assertRaisesRegex(ProjectValidationError, "mixed save_generation"):
            ProjectStore().load(self.root)
        manifest_path.write_bytes(original)

        self.rewrite_registered(
            "decisions.json",
            lambda value: value["data"]["decisions"][0].update({"source_round": "missing"}),
        )
        with self.assertRaisesRegex(ProjectValidationError, "invalid round/question source"):
            ProjectStore().load(self.root)

    def test_invalid_trace_provenance_is_rejected(self) -> None:
        self.commit_one()

        def corrupt(value) -> None:
            event = next(
                item for item in value["data"]["records"] if item["action"] == "SYNTHESIZE"
            )
            event["details"]["canonical_rule"] = "forged"

        self.rewrite_registered("trace.json", corrupt)
        with self.assertRaisesRegex(ProjectValidationError, "mismatched canonical_rule"):
            ProjectStore().load(self.root)

    def test_committed_owner_answer_cannot_be_edited_in_place(self) -> None:
        self.commit_one()
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.project.workspace.record_owner_answer("round-1", "question-1", "A")

    def test_round_recommendation_tampering_is_rejected(self) -> None:
        self.commit_one()
        self.rewrite_registered(
            "rounds.json",
            lambda value: value["data"]["rounds"][0]["questions"][0][
                "recommendation"
            ].update({"reason": "rewritten advice"}),
        )
        with self.assertRaisesRegex(ProjectValidationError, "recommendation disagrees"):
            ProjectStore().load(self.root)

    def test_concept_source_provenance_tampering_is_rejected(self) -> None:
        self.project.start_session("session-concept")
        self.project.set_draft(simple_draft(with_concept=True))
        self.project.answer_draft("question-1", "B")
        self.project.lock_draft()

        def corrupt(value) -> None:
            value["data"]["current"][0]["provenance"]["current_source"][
                "owner_answer"
            ] = ["A"]

        self.rewrite_registered("concepts.json", corrupt)
        with self.assertRaisesRegex(ProjectValidationError, "current provenance disagrees"):
            ProjectStore().load(self.root)

    def test_stale_cache_regenerates_and_artifacts_report_stale(self) -> None:
        self.commit_one()
        self.project.compile_artifacts()
        self.assertEqual("CURRENT", self.project.artifact_status("generated/context_handoff.md"))
        cache = self.root / "cache/current_state.json"
        cache.write_text("stale", encoding="utf-8")
        loaded = ProjectStore().load(self.root)
        self.assertEqual(loaded.save_generation, json.loads(cache.read_text())["source_save_generation"])
        self.project.save()
        resumed = ProjectStore().load(self.root)
        self.assertEqual("STALE", resumed.artifact_status("generated/context_handoff.md"))

    def test_storage_checkpoints_do_not_fabricate_semantic_history(self) -> None:
        self.commit_one()
        trace_ids = tuple(item.trace_id for item in self.project.workspace.trace.records)
        generation = self.project.manifest.save_generation
        self.project.save()
        self.project.save()
        self.assertEqual(generation + 2, self.project.manifest.save_generation)
        self.assertEqual(trace_ids, tuple(item.trace_id for item in self.project.workspace.trace.records))

    def test_interrupted_save_artifacts_block_activation_for_review(self) -> None:
        candidate = self.root.parent / f".{self.root.name}.candidate-owner-review"
        candidate.mkdir()
        with self.assertRaisesRegex(ProjectValidationError, "owner review"):
            ProjectStore().load(self.root)


if __name__ == "__main__":
    unittest.main()
