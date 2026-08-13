from __future__ import annotations

import json
import hashlib
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from design_flow import (
    CommandRunner,
    ConceptMaturity,
    ConceptStatus,
    CoreConcept,
    DesignFlowMode,
    DraftDecisionPlan,
    DraftQuestion,
    DraftRound,
    PersistentProject,
    ProjectStore,
    ProjectValidationError,
    QuestionOption,
    QuestionType,
    Recommendation,
    TraceAction,
    compile_context_handoff,
    compile_unresolved_register,
)
from design_flow.session import encode_draft

from design_flow.persistence import canonical_json_bytes
from tests.test_v02_persistence import simple_draft


class IntegrityCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "project"
        self.project = PersistentProject.create(
            self.root,
            project_id="integrity-project",
            name="Integrity Project",
            description="Focused repair test.",
            mode=DesignFlowMode.DISCOVERY,
            authority="Owner",
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
        self_hash = hashlib.sha256(canonical_json_bytes(manifest)).hexdigest()
        for entry in manifest["authoritative_files"]:
            if entry["path"] == "manifest.json":
                entry["content_hash"] = self_hash
        manifest_path.write_bytes(canonical_json_bytes(manifest))


class SupersessionActivationTests(IntegrityCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.start_session("chain-session")
        self._commit("draft-a", "round-a", "decision-a", "A")
        self._commit("draft-b", "round-b", "decision-b", "B", "decision-a")
        self._commit("draft-c", "round-c", "decision-c", "A", "decision-b")

    def _commit(
        self,
        draft_id: str,
        round_id: str,
        decision_id: str,
        answer: str,
        supersedes: str | None = None,
    ) -> None:
        draft = simple_draft(draft_id=draft_id, round_id=round_id, decision_id=decision_id)
        plan = replace(
            draft.decisions[0],
            supersedes_decision=supersedes,
            supersession_notes="Explicit chain correction." if supersedes else "",
        )
        self.project.set_draft(replace(draft, decisions=(plan,)))
        self.project.answer_draft("question-1", answer)
        self.project.lock_draft()

    def test_valid_linear_chain_survives_exactly(self) -> None:
        loaded = PersistentProject.resume(self.root)
        self.assertEqual((), loaded.workspace.ledger.get("decision-a").supersedes)
        self.assertEqual(("decision-a",), loaded.workspace.ledger.get("decision-b").supersedes)
        self.assertEqual(
            ("decision-a", "decision-b"),
            loaded.workspace.ledger.get("decision-c").supersedes,
        )

    def test_forged_superseded_status_is_rejected(self) -> None:
        self.rewrite_registered(
            "decisions.json",
            lambda value: value["data"]["decisions"][2].update({"status": "SUPERSEDED"}),
        )
        with self.assertRaisesRegex(ProjectValidationError, "no replacement"):
            ProjectStore().load(self.root)

    def test_forged_and_missing_ancestry_are_rejected(self) -> None:
        for ancestry in (["decision-a", "decision-b", "forged"], ["decision-b"]):
            with self.subTest(ancestry=ancestry):
                original = (self.root / "decisions.json").read_bytes()
                manifest = (self.root / "manifest.json").read_bytes()
                self.rewrite_registered(
                    "decisions.json",
                    lambda value, ancestry=ancestry: value["data"]["decisions"][2].update(
                        {"supersedes": ancestry}
                    ),
                )
                with self.assertRaisesRegex(ProjectValidationError, "ancestry disagrees"):
                    ProjectStore().load(self.root)
                (self.root / "decisions.json").write_bytes(original)
                (self.root / "manifest.json").write_bytes(manifest)

    def test_duplicate_direct_edge_is_rejected(self) -> None:
        self.rewrite_registered(
            "decisions.json",
            lambda value: value["data"]["relationships"].append(
                dict(value["data"]["relationships"][0])
            ),
        )
        with self.assertRaisesRegex(ProjectValidationError, "Duplicate SUPERSEDES"):
            ProjectStore().load(self.root)

    def test_orphaned_supersede_trace_is_rejected(self) -> None:
        def inject(value) -> None:
            value["data"]["records"].append(
                {
                    "trace_id": "trace-9999",
                    "action": "SUPERSEDE",
                    "entity_type": "decision",
                    "entity_id": "decision-c",
                    "details": {"replaced_by": "forged", "notes": "forged"},
                }
            )

        self.rewrite_registered("trace.json", inject)
        with self.assertRaisesRegex(ProjectValidationError, "Orphaned SUPERSEDE"):
            ProjectStore().load(self.root)

    def test_missing_supersede_trace_is_rejected(self) -> None:
        decisions = json.loads((self.root / "decisions.json").read_text())
        trace_id = next(
            item
            for item in decisions["data"]["decisions"][0]["trace_refs"]
            if item in decisions["data"]["decisions"][1]["trace_refs"]
        )
        self.rewrite_registered(
            "trace.json",
            lambda value: value["data"].update(
                {"records": [item for item in value["data"]["records"] if item["trace_id"] != trace_id]}
            ),
        )
        self.rewrite_registered(
            "decisions.json",
            lambda value: [
                item.update({"trace_refs": [ref for ref in item["trace_refs"] if ref != trace_id]})
                for item in value["data"]["decisions"]
            ],
        )
        with self.assertRaisesRegex(ProjectValidationError, "lacks matching TRACE"):
            ProjectStore().load(self.root)


class CommittedHistoryTests(IntegrityCase):
    def test_project_round_question_are_deeply_immutable_but_draft_replaces(self) -> None:
        self.commit_one()
        project = self.project.workspace.project
        design_round = self.project.workspace.rounds.get("round-1")
        question = design_round.question("question-1")
        attempts = (
            lambda: setattr(project, "name", "forged"),
            lambda: setattr(project, "description", "forged"),
            lambda: setattr(project, "authority", "forged"),
            lambda: setattr(project, "current_mode", DesignFlowMode.REPAIR),
            lambda: setattr(project, "unresolved_areas", ("forged",)),
            lambda: setattr(design_round, "topic", "forged"),
            lambda: setattr(design_round, "purpose", "forged"),
            lambda: setattr(design_round, "prerequisites", ("forged",)),
            lambda: setattr(design_round, "derived_rules", ("forged",)),
            lambda: setattr(design_round, "unresolved", ("forged",)),
            lambda: setattr(design_round, "status", design_round.status),
            lambda: setattr(design_round, "trace_refs", ("forged",)),
            lambda: setattr(question, "text", "forged"),
            lambda: setattr(question, "options", ()),
            lambda: setattr(question, "recommendation", Recommendation(("B",), "forged")),
            lambda: setattr(question, "owner_answer", None),
            lambda: setattr(question, "answer_status", question.answer_status),
            lambda: setattr(question, "derived_implications", ("forged",)),
            lambda: setattr(question, "trace_refs", ("forged",)),
        )
        for attempt in attempts:
            with self.assertRaises((FrozenInstanceError, AttributeError)):
                attempt()
        with self.assertRaises(TypeError):
            design_round.owner_answer_set["forged"] = question.owner_answer

        draft = simple_draft(draft_id="editable", round_id="editable-round")
        updated = draft.answer("question-1", "A")
        self.assertEqual({}, dict(draft.answers))
        self.assertEqual("A", updated.answers["question-1"])


class UnresolvedAndRunnerTests(IntegrityCase):
    def test_round_only_unresolved_reaches_every_surface(self) -> None:
        self.project.start_session("round-only")
        draft = replace(simple_draft(), decisions=())
        self.project.set_draft(draft)
        self.project.answer_draft("question-1", "A depending on context")
        self.project.lock_draft()
        seam = "Resolve the boundary for A: depending on context."
        self.assertIn(seam, compile_unresolved_register(self.project.workspace))
        runner = CommandRunner(self.project)
        self.assertIn(seam, runner.execute("UNRESOLVED"))
        self.assertIn(seam, compile_context_handoff(self.project.workspace, self.project.sessions))
        self.assertIn(seam, self.project.session_brief().unresolved)
        self.assertIn(seam, self.project.session_brief().recommendation_reason)
        unresolved = json.loads((self.root / "unresolved.json").read_text())["data"]["items"]
        self.assertIn(seam, unresolved)

    def test_concept_only_unresolved_and_empty_register_are_consistent(self) -> None:
        self.assertEqual((), compile_unresolved_register(self.project.workspace))
        runner = CommandRunner(self.project)
        self.assertEqual("No unresolved items.", runner.execute("UNRESOLVED"))
        self.assertEqual((), self.project.session_brief().unresolved)
        self.assertIn("coherent", self.project.session_brief().recommendation_reason)
        self.assertIn("- None.", compile_context_handoff(self.project.workspace))
        concept = CoreConcept(
            "concept-only",
            "CONCEPT_ONLY",
            "0.2.0",
            ConceptStatus.UNRESOLVED,
            ConceptMaturity.DISPUTED,
            "test",
            "A concept-only seam.",
            unresolved=("Resolve concept-only seam.",),
        )
        self.project.workspace.concepts.restore((), (concept,), ())
        seam = "Resolve concept-only seam."
        self.assertIn(seam, compile_unresolved_register(self.project.workspace))
        self.assertIn(seam, runner.execute("UNRESOLVED"))
        self.assertIn(seam, compile_context_handoff(self.project.workspace))
        self.assertIn(seam, self.project.session_brief().unresolved)
        self.assertIn("concept-only", self.project.session_brief().recommendation_reason)

    def test_command_surface_imports_and_completes_real_round(self) -> None:
        self.project.start_session("runner-e2e")
        draft_path = Path(self.temp.name) / "draft.json"
        draft_path.write_text(json.dumps(encode_draft(simple_draft())), encoding="utf-8")
        runner = CommandRunner(self.project)
        self.assertIn("Imported draft", runner.execute(f"IMPORT DRAFT {draft_path}"))
        self.assertIn("saved", runner.execute("ANSWER question-1 B"))
        self.assertIn("Use beta.", runner.execute("PREVIEW"))
        self.assertIn("Committed round", runner.execute("LOCK"))
        self.assertIn("generation", runner.execute("SAVE"))
        runner.execute("END SESSION")
        resumed = PersistentProject.resume(self.root)
        self.assertEqual("Use beta.", resumed.workspace.ledger.get("decision-1").canonical_rule)


class PromotionFailureTests(IntegrityCase):
    def test_candidate_construction_failure_never_moves_prior_target(self) -> None:
        self.project.start_session("construction")
        generation = self.project.manifest.save_generation
        with patch("design_flow.persistence._write_bytes", side_effect=OSError("write fail")):
            with self.assertRaises(OSError):
                self.project.save()
        self.assertEqual(generation, ProjectStore().load(self.root).save_generation)
        self.assertFalse(any(self.root.parent.glob(f".{self.root.name}.candidate-*")))

    def test_candidate_validation_failure_never_moves_prior_target(self) -> None:
        self.project.start_session("validation")
        generation = self.project.manifest.save_generation
        original_load = ProjectStore.load

        def reject_candidate(store, path, **kwargs):
            if kwargs.get("check_recovery") is False:
                raise ProjectValidationError("candidate rejected")
            return original_load(store, path, **kwargs)

        with patch.object(ProjectStore, "load", new=reject_candidate):
            with self.assertRaisesRegex(ProjectValidationError, "candidate rejected"):
                self.project.save()
        self.assertEqual(generation, ProjectStore().load(self.root).save_generation)
        self.assertFalse(any(self.root.parent.glob(f".{self.root.name}.candidate-*")))

    def test_target_to_backup_failure_leaves_prior_and_draft(self) -> None:
        self.project.start_session("promotion")
        self.project.set_draft(simple_draft())
        self.project.answer_draft("question-1", "B")
        generation = self.project.manifest.save_generation
        with patch("design_flow.persistence.os.replace", side_effect=OSError("backup fail")):
            with self.assertRaisesRegex(ProjectValidationError, "draft preserved"):
                self.project.lock_draft()
        self.assertIsNotNone(self.project.draft)
        self.assertEqual(generation, ProjectStore().load(self.root).save_generation)

    def test_candidate_to_target_failure_rolls_back_prior(self) -> None:
        self.project.start_session("promotion-fail")
        self.project.set_draft(simple_draft())
        self.project.answer_draft("question-1", "B")
        generation = self.project.manifest.save_generation
        original_replace = os.replace
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("promotion fail")
            return original_replace(source, target)

        with patch("design_flow.persistence.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(ProjectValidationError, "draft preserved"):
                self.project.lock_draft()
        self.assertIsNotNone(self.project.draft)
        self.assertEqual((), self.project.workspace.rounds.rounds)
        self.assertTrue(self.root.is_dir())
        self.assertEqual(generation, ProjectStore().load(self.root).save_generation)
        self.assertFalse(any(self.root.parent.glob(f".{self.root.name}.candidate-*")))
        self.assertFalse(any(self.root.parent.glob(f".{self.root.name}.backup-*")))

    def test_rollback_failure_preserves_both_recovery_artifacts(self) -> None:
        self.project.start_session("rollback-fail")
        self.project.set_draft(simple_draft())
        self.project.answer_draft("question-1", "B")
        original_replace = os.replace
        calls = 0

        def fail_after_backup(source, target):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("rename fail")
            return original_replace(source, target)

        with patch("design_flow.persistence.os.replace", side_effect=fail_after_backup):
            with self.assertRaisesRegex(ProjectValidationError, "draft preserved"):
                self.project.lock_draft()
        self.assertIsNotNone(self.project.draft)
        self.assertEqual((), self.project.workspace.rounds.rounds)
        self.assertTrue(any(self.root.parent.glob(f".{self.root.name}.candidate-*")))
        self.assertTrue(any(self.root.parent.glob(f".{self.root.name}.backup-*")))

    def test_backup_cleanup_failure_is_committed_with_truthful_warning(self) -> None:
        self.project.start_session("cleanup")
        self.project.set_draft(simple_draft())
        self.project.answer_draft("question-1", "B")
        with patch("design_flow.persistence.shutil.rmtree", side_effect=OSError("cleanup fail")):
            committed = self.project.lock_draft()
        self.assertEqual("round-1", committed.round_id)
        self.assertIn("promotion committed", self.project.last_storage_warning)
        loaded = ProjectStore().load(self.root, check_recovery=False)
        self.assertEqual("Use beta.", loaded.workspace.ledger.get("decision-1").canonical_rule)
        with self.assertRaisesRegex(ProjectValidationError, "owner review"):
            ProjectStore().load(self.root)


class SessionValidationTests(IntegrityCase):
    def test_resume_reuses_one_open_session(self) -> None:
        self.project.start_session("open-session")
        resumed = PersistentProject.resume(self.root)
        self.assertEqual("open-session", resumed.active_session_id)
        resumed.end_session()
        self.assertIsNone(PersistentProject.resume(self.root).active_session)

    def test_session_round_and_generation_inconsistency_is_rejected(self) -> None:
        self.project.start_session("session-invalid")
        cases = (
            lambda item: item.update({"rounds_touched": ["unknown"]}),
            lambda item: item.update({"rounds_committed": ["unknown"]}),
            lambda item: item.update({"save_generations": [9999]}),
        )
        for transform in cases:
            with self.subTest(transform=transform):
                original = (self.root / "sessions.json").read_bytes()
                manifest = (self.root / "manifest.json").read_bytes()
                self.rewrite_registered(
                    "sessions.json",
                    lambda value, transform=transform: transform(
                        value["data"]["sessions"][0]
                    ),
                )
                with self.assertRaises(ProjectValidationError):
                    ProjectStore().load(self.root)
                (self.root / "sessions.json").write_bytes(original)
                (self.root / "manifest.json").write_bytes(manifest)

    def test_multiple_open_sessions_are_rejected(self) -> None:
        self.project.start_session("session-open")

        def duplicate(value) -> None:
            second = dict(value["data"]["sessions"][0])
            second["session_id"] = "session-open-2"
            value["data"]["sessions"].append(second)

        self.rewrite_registered("sessions.json", duplicate)
        with self.assertRaisesRegex(ProjectValidationError, "At most one"):
            ProjectStore().load(self.root)

    def test_committed_round_must_be_touched(self) -> None:
        self.commit_one()
        self.rewrite_registered(
            "sessions.json",
            lambda value: value["data"]["sessions"][0].update({"rounds_touched": []}),
        )
        with self.assertRaisesRegex(ProjectValidationError, "never touched"):
            ProjectStore().load(self.root)


if __name__ == "__main__":
    unittest.main()
