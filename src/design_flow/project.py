"""Persistent project façade: drafts, sessions, atomic commits, and compilation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .handoff import compile_context_handoff, recommend_next_round
from .intake import DesignFlowWorkspace
from .model import DesignFlowMode, DesignRound, Question
from .persistence import (
    APPLICATION_VERSION,
    ArtifactContent,
    LoadedProject,
    ProjectManifest,
    ProjectStore,
    ProjectValidationError,
    SourceReference,
)
from .session import (
    DraftConceptAction,
    DraftPreview,
    DraftRound,
    SessionRecord,
    utc_now,
    decode_draft,
)
from .unresolved import compile_unresolved_register


@dataclass(slots=True, frozen=True)
class SessionBrief:
    project_id: str
    name: str
    mode: str
    current_rules: tuple[str, ...]
    unresolved: tuple[str, ...]
    last_completed_round: str | None
    recommended_next_round: str
    recommendation_reason: str


class _UnchangedDraft:
    pass


_UNCHANGED_DRAFT = _UnchangedDraft()


class PersistentProject:
    """Operate one durable project without conflating it with a session."""

    def __init__(self, loaded: LoadedProject, store: ProjectStore | None = None) -> None:
        self.path = loaded.path
        self.workspace = loaded.workspace
        self.manifest = loaded.manifest
        self.sessions = loaded.sessions
        self.draft = loaded.draft
        self.sources = loaded.sources
        self.store = store or ProjectStore()
        self.last_storage_warning: str | None = None
        open_sessions = [item.session_id for item in self.sessions if item.ended_at is None]
        self.active_session_id: str | None = open_sessions[0] if open_sessions else None

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        project_id: str,
        name: str,
        description: str,
        mode: DesignFlowMode,
        authority: str,
        source_context: tuple[str, ...] = (),
        unresolved_areas: tuple[str, ...] = (),
        store: ProjectStore | None = None,
    ) -> "PersistentProject":
        storage = store or ProjectStore()
        workspace = DesignFlowWorkspace.create(
            project_id=project_id,
            name=name,
            description=description,
            mode=mode,
            authority=authority,
            source_context=source_context,
            unresolved_areas=unresolved_areas,
        )
        loaded = storage.create(path, workspace)
        return cls(loaded, storage)

    @classmethod
    def resume(
        cls, path: str | Path, *, store: ProjectStore | None = None
    ) -> "PersistentProject":
        storage = store or ProjectStore()
        return cls(storage.load(path), storage)

    @property
    def active_session(self) -> SessionRecord | None:
        return next(
            (item for item in self.sessions if item.session_id == self.active_session_id),
            None,
        )

    def start_session(self, session_id: str | None = None) -> SessionRecord:
        if self.active_session is not None:
            raise ValueError("A session is already active")
        identifier = session_id or f"session-{uuid4().hex[:12]}"
        if any(item.session_id == identifier for item in self.sessions):
            raise ValueError(f"Session already exists: {identifier}")
        session = SessionRecord(identifier, self.workspace.project.project_id, utc_now())
        session = session.record_generation(self.manifest.save_generation + 1)
        sessions = (*self.sessions, session)
        self._checkpoint(sessions=sessions)
        self.active_session_id = identifier
        return session

    def end_session(self) -> SessionRecord:
        session = self._require_session().end()
        sessions = self._replace_session(session)
        self._checkpoint(sessions=sessions)
        persisted = self._require_session()
        self.active_session_id = None
        return persisted

    def add_source(self, source: SourceReference) -> None:
        if any(item.source_id == source.source_id for item in self.sources):
            raise ValueError(f"Source already exists: {source.source_id}")
        sources = (*self.sources, source)
        self._checkpoint(sources=sources)

    def source_status(self, source_id: str) -> str:
        source = next((item for item in self.sources if item.source_id == source_id), None)
        if source is None:
            raise KeyError(f"Unknown source: {source_id}")
        if source.local_path is not None:
            return "AVAILABLE" if (self.path / source.local_path).is_file() else "UNAVAILABLE"
        return "EXTERNAL_UNCHECKED"

    def artifact_status(self, path: str) -> str:
        loaded = LoadedProject(
            self.path,
            self.workspace,
            self.manifest,
            self.sessions,
            self.draft,
            self.sources,
        )
        return loaded.artifact_status(path)

    def set_draft(self, draft: DraftRound) -> None:
        if self.draft is not None and self.draft.draft_id != draft.draft_id:
            raise ValueError("Abandon the current draft before replacing it")
        session = self._require_session().touch_round(draft.round_id)
        sessions = self._replace_session(session)
        self._checkpoint(sessions=sessions, draft=draft)

    def import_draft(self, path: str | Path) -> DraftRound:
        """Originate working state from one strict, non-authoritative JSON draft."""

        source = Path(path)
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
            draft = decode_draft(value, "imported draft")
        except (OSError, TypeError, ValueError) as error:
            raise ValueError(f"Cannot import draft {source}: {error}") from error
        self.set_draft(draft)
        return draft

    def answer_draft(self, question_id: str, raw_value: str) -> DraftRound:
        draft = self._require_draft().answer(question_id, raw_value)
        session = self._require_session().touch_round(draft.round_id)
        sessions = self._replace_session(session)
        self._checkpoint(sessions=sessions, draft=draft)
        return draft

    def abandon_draft(self) -> None:
        self._require_draft()
        self._checkpoint(draft=None)

    def preview_draft(self) -> DraftPreview:
        draft = self._require_draft()
        if not draft.complete:
            missing = tuple(
                item.question_id for item in draft.questions if item.question_id not in draft.answers
            )
            return DraftPreview(
                "DRAFT PREVIEW — NON-AUTHORITATIVE",
                (),
                (),
                (),
                (),
                tuple(f"Missing owner answer: {item}" for item in missing),
            )
        candidate = self.store.clone_workspace(self.workspace)
        try:
            affected_before = {item.concept_id for item in candidate.concepts.affected}
            self._apply_draft(candidate, draft)
            affected_after = {item.concept_id for item in candidate.concepts.affected}
            return DraftPreview(
                "DRAFT PREVIEW — NON-AUTHORITATIVE",
                tuple(candidate.rounds.get(draft.round_id).derived_rules),
                tuple(
                    f"{item.supersedes_decision} -> {item.decision_id}"
                    for item in draft.decisions
                    if item.supersedes_decision is not None
                ),
                tuple(sorted(affected_after - affected_before)),
                compile_unresolved_register(candidate),
            )
        except (KeyError, TypeError, ValueError) as error:
            return DraftPreview(
                "DRAFT PREVIEW — NON-AUTHORITATIVE", (), (), (), (), (str(error),)
            )

    def lock_draft(self) -> DesignRound:
        """Validate and promote one complete draft at the documented commit point."""

        draft = self._require_draft()
        session = self._require_session()
        if not draft.complete:
            raise ProjectValidationError("A round cannot be locked until every question is answered")
        candidate = self.store.clone_workspace(self.workspace)
        try:
            committed_round = self._apply_draft(candidate, draft)
            sessions = self._replace_session(session.commit_round(draft.round_id))
            predicted_generation = self.manifest.save_generation + 1
            sessions = self._record_generation(sessions, predicted_generation)
            manifest = self.store.save(
                self.path,
                candidate,
                sessions=sessions,
                draft=None,
                sources=self.sources,
                prior_manifest=self.manifest,
            )
        except Exception as error:
            raise ProjectValidationError(
                f"Round commit failed; draft preserved and no authority activated: {error}"
            ) from error
        self.workspace = candidate
        self.sessions = sessions
        self.draft = None
        self.manifest = manifest
        self.last_storage_warning = self.store.last_recovery_warning
        return committed_round

    def save(self) -> ProjectManifest:
        return self._checkpoint()

    def compile_artifacts(self) -> tuple[str, str]:
        living = self.workspace.render_application_document()
        handoff = compile_context_handoff(self.workspace, self.sessions)
        paths = ("generated/living_application.md", "generated/context_handoff.md")
        sessions = self.sessions
        session = self.active_session
        if session is not None:
            sessions = self._replace_session(session.record_artifacts(paths))
        self._checkpoint(
            sessions=sessions,
            artifacts={
                paths[0]: ArtifactContent(
                    "living_application", "design_flow.living_application", APPLICATION_VERSION, living
                ),
                paths[1]: ArtifactContent(
                    "context_handoff", "design_flow.context_handoff", APPLICATION_VERSION, handoff
                ),
            },
        )
        return paths

    def session_brief(self) -> SessionBrief:
        state = self.workspace.state_compiler.compile(
            self.workspace.project, self.workspace.ledger
        )
        recommendation = recommend_next_round(self.workspace)
        rounds = self.workspace.rounds.rounds
        return SessionBrief(
            self.workspace.project.project_id,
            self.workspace.project.name,
            self.workspace.project.current_mode.value,
            tuple(item.canonical_rule for item in state.decisions),
            compile_unresolved_register(self.workspace),
            rounds[-1].round_id if rounds else None,
            recommendation.topic,
            recommendation.reason,
        )

    def _checkpoint(
        self,
        *,
        sessions: tuple[SessionRecord, ...] | None = None,
        draft: DraftRound | None | _UnchangedDraft = _UNCHANGED_DRAFT,
        sources: tuple[SourceReference, ...] | None = None,
        artifacts: dict[str, ArtifactContent] | None = None,
    ) -> ProjectManifest:
        next_sessions = self.sessions if sessions is None else sessions
        next_draft = self.draft if isinstance(draft, _UnchangedDraft) else draft
        next_sources = self.sources if sources is None else sources
        next_generation = self.manifest.save_generation + 1
        if self.active_session_id is not None:
            next_sessions = self._record_generation(next_sessions, next_generation)
        manifest = self.store.save(
            self.path,
            self.workspace,
            sessions=next_sessions,
            draft=next_draft,
            sources=next_sources,
            artifacts=artifacts,
            prior_manifest=self.manifest,
        )
        self.sessions = next_sessions
        self.draft = next_draft
        self.sources = next_sources
        self.manifest = manifest
        self.last_storage_warning = self.store.last_recovery_warning
        return manifest

    def storage_warning_suffix(self) -> str:
        if self.last_storage_warning is None:
            return ""
        return f"\nWARNING: {self.last_storage_warning}"

    def _require_session(self) -> SessionRecord:
        session = self.active_session
        if session is None:
            raise ValueError("Start a session before changing working state")
        return session

    def _require_draft(self) -> DraftRound:
        if self.draft is None:
            raise ValueError("No draft round is active")
        return self.draft

    def _replace_session(self, replacement: SessionRecord) -> tuple[SessionRecord, ...]:
        return tuple(
            replacement if item.session_id == replacement.session_id else item
            for item in self.sessions
        )

    def _record_generation(
        self, sessions: tuple[SessionRecord, ...], generation: int
    ) -> tuple[SessionRecord, ...]:
        return tuple(
            item.record_generation(generation)
            if item.session_id == self.active_session_id
            else item
            for item in sessions
        )

    @staticmethod
    def _apply_draft(workspace: DesignFlowWorkspace, draft: DraftRound) -> DesignRound:
        design_round = workspace.start_round(
            DesignRound(draft.round_id, draft.topic, draft.purpose, draft.prerequisites)
        )
        for item in draft.questions:
            workspace.add_question(
                draft.round_id,
                Question(
                    item.question_id,
                    item.text,
                    item.question_type,
                    item.options,
                    item.recommendation,
                ),
            )
        for item in draft.questions:
            workspace.record_owner_answer(
                draft.round_id, item.question_id, draft.answers[item.question_id]
            )
        for plan in draft.decisions:
            decision = workspace.synthesize_decision(
                draft.round_id,
                plan.question_id,
                decision_id=plan.decision_id,
                scope=plan.scope,
                rule_mapping=plan.rules(),
                dependencies=plan.dependencies,
                unresolved_consequences=plan.unresolved_consequences,
            )
            if plan.supersedes_decision is not None:
                workspace.ledger.supersede(
                    plan.supersedes_decision,
                    decision.decision_id,
                    notes=plan.supersession_notes,
                )
                decision = workspace.ledger.get(decision.decision_id)
            concept = plan.concept
            if concept is None:
                continue
            if concept.action is DraftConceptAction.REGISTER:
                workspace.register_concept_from_decision(
                    decision,
                    concept_id=concept.concept_id,
                    canonical_name=concept.canonical_name,
                    definition=concept.definition,
                    version=concept.version,
                    maturity=concept.maturity,
                    owns=concept.owns,
                    does_not_own=concept.does_not_own,
                    boundaries=concept.boundaries,
                    dependencies=concept.dependencies,
                    relations=concept.relations,
                    unresolved=concept.unresolved,
                )
            else:
                workspace.concepts.revise(
                    concept.concept_id,
                    version=concept.version,
                    definition=concept.definition,
                    source_decision=decision,
                    maturity=concept.maturity,
                    unresolved=concept.unresolved,
                )
        return workspace.rounds.get(draft.round_id)
