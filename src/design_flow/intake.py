"""Project intake and the canonical semantic orchestration surface."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .concepts import CoreConceptRegistry
from .decisions import CurrentStateCompiler, DecisionLedger, DecisionSynthesizer
from .documents import LivingApplicationDocumentRenderer
from .model import (
    CoreConcept,
    ConflictRecord,
    Decision,
    DesignFlowMode,
    DesignRound,
    OwnerAnswer,
    Project,
    Question,
    TraceAction,
    TraceRecord,
)
from .rounds import RoundManager
from .trace import TraceLog
from .unresolved import compile_unresolved_register


class DesignFlowWorkspace:
    """Canonical integrity boundary for complete Design Flow behavior.

    The workspace owns the shared TRACE and wires decision supersession to
    concept invalidation. Lower-level classes remain useful primitives, but a
    caller composing them directly must provide equivalent cross-module wiring.
    """

    def __init__(self, project: Project) -> None:
        self.project = project
        self.trace = TraceLog()
        self.rounds = RoundManager(project, self.trace)
        self.synthesizer = DecisionSynthesizer(self.trace)
        self.ledger = DecisionLedger(self.trace)
        self.concepts = CoreConceptRegistry(self.trace, self.ledger.get)
        self.ledger.add_supersession_listener(self.concepts.mark_affected_by_supersession)
        self.state_compiler = CurrentStateCompiler()
        self.document_renderer = LivingApplicationDocumentRenderer(self.trace)
        self.trace.record(
            TraceAction.REGISTER_PROJECT,
            "project",
            project.project_id,
            name=project.name,
            mode=project.current_mode.value,
            authority=project.authority,
        )

    @classmethod
    def create(
        cls,
        *,
        project_id: str,
        name: str,
        description: str,
        mode: DesignFlowMode,
        authority: str,
        source_context: tuple[str, ...] = (),
        unresolved_areas: tuple[str, ...] = (),
    ) -> "DesignFlowWorkspace":
        return cls(
            Project(
                project_id=project_id,
                name=name,
                description=description,
                current_mode=mode,
                authority=authority,
                source_context=source_context,
                unresolved_areas=unresolved_areas,
            )
        )

    @classmethod
    def restore(
        cls,
        *,
        project: Project,
        trace_records: tuple[TraceRecord, ...],
        rounds: tuple[DesignRound, ...],
        decisions: tuple[Decision, ...],
        relationships: tuple[ConflictRecord, ...],
        current_concepts: tuple[CoreConcept, ...],
        affected_concepts: tuple[CoreConcept, ...],
        concept_history: tuple[CoreConcept, ...],
    ) -> "DesignFlowWorkspace":
        """Rehydrate a validated workspace without creating semantic events."""

        workspace = cls.__new__(cls)
        workspace.project = project
        workspace.trace = TraceLog()
        workspace.trace.restore(trace_records)
        workspace.rounds = RoundManager(project, workspace.trace)
        workspace.rounds.restore(rounds)
        workspace.synthesizer = DecisionSynthesizer(workspace.trace)
        workspace.ledger = DecisionLedger(workspace.trace)
        workspace.ledger.restore(decisions, relationships)
        workspace.concepts = CoreConceptRegistry(workspace.trace, workspace.ledger.get)
        workspace.concepts.restore(current_concepts, affected_concepts, concept_history)
        workspace.ledger.add_supersession_listener(
            workspace.concepts.mark_affected_by_supersession
        )
        workspace.state_compiler = CurrentStateCompiler()
        workspace.document_renderer = LivingApplicationDocumentRenderer(workspace.trace)
        return workspace

    def start_round(self, design_round: DesignRound) -> DesignRound:
        return self.rounds.register_round(design_round)

    def add_question(self, round_id: str, question: Question) -> Question:
        return self.rounds.add_question(round_id, question)

    def record_owner_answer(self, round_id: str, question_id: str, value: str) -> OwnerAnswer:
        return self.rounds.record_owner_answer(round_id, question_id, value)

    def synthesize_decision(
        self,
        round_id: str,
        question_id: str,
        *,
        decision_id: str,
        scope: str,
        rule_mapping: Mapping[str | tuple[str, ...], str],
        dependencies: tuple[str, ...] = (),
        unresolved_consequences: tuple[str, ...] = (),
    ) -> Decision:
        decision = self.synthesizer.synthesize(
            self.rounds.get(round_id),
            question_id,
            decision_id=decision_id,
            scope=scope,
            rule_mapping=rule_mapping,
            dependencies=dependencies,
            unresolved_consequences=unresolved_consequences,
        )
        registered = self.ledger.register(decision)
        self.rounds.record_synthesis(round_id, registered.canonical_rule)
        return registered

    def register_concept_from_decision(self, decision: Decision, **fields: Any) -> CoreConcept:
        return self.concepts.register_from_decision(decision, **fields)

    def render_application_document(self) -> str:
        state = self.state_compiler.compile(self.project, self.ledger)
        return self.document_renderer.render(
            self.project,
            state,
            self.concepts,
            self.ledger,
            compile_unresolved_register(self),
        )

    def record_application_document_generation(self) -> str:
        state = self.state_compiler.compile(self.project, self.ledger)
        return self.document_renderer.record_generation(self.project, state)
