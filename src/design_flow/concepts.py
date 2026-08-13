"""PSG-informed core-concept registration from structured decisions."""

from __future__ import annotations

from dataclasses import replace

from .model import CoreConcept, Decision, DecisionStatus, TraceAction
from .trace import TraceLog


class CoreConceptRegistry:
    """Maintain current concepts and superseded concept versions."""

    def __init__(self, trace: TraceLog) -> None:
        self.trace = trace
        self._current: dict[str, CoreConcept] = {}
        self._history: list[CoreConcept] = []

    @property
    def concepts(self) -> tuple[CoreConcept, ...]:
        return tuple(self._current.values())

    @property
    def history(self) -> tuple[CoreConcept, ...]:
        return tuple(self._history)

    def get(self, concept_id: str) -> CoreConcept:
        try:
            return self._current[concept_id]
        except KeyError as error:
            raise KeyError(f"Unknown concept: {concept_id}") from error

    def register_from_decision(
        self,
        decision: Decision,
        *,
        concept_id: str,
        canonical_name: str,
        definition: str,
        owns: tuple[str, ...] = (),
        does_not_own: tuple[str, ...] = (),
        boundaries: tuple[str, ...] = (),
        dependencies: tuple[str, ...] = (),
        relations: tuple[str, ...] = (),
        unresolved: tuple[str, ...] = (),
    ) -> CoreConcept:
        if concept_id in self._current:
            raise ValueError(f"Concept already exists: {concept_id}")
        if decision.status not in {
            DecisionStatus.SYNTHESIZED,
            DecisionStatus.TESTED,
            DecisionStatus.RATIFIED,
            DecisionStatus.UNRESOLVED,
        }:
            raise ValueError("Concepts require a synthesized or explicitly unresolved decision")
        if not decision.trace_refs:
            raise ValueError("Concept source decisions require provenance")

        concept = CoreConcept(
            concept_id=concept_id,
            canonical_name=canonical_name,
            version="0.1.0",
            status=decision.status,
            maturity=decision.status,
            scope=decision.scope,
            definition=definition,
            owns=owns,
            does_not_own=does_not_own,
            boundaries=boundaries,
            dependencies=dependencies,
            relations=relations,
            source_decisions=(decision.decision_id,),
            unresolved=tuple(dict.fromkeys((*unresolved, *decision.unresolved_consequences))),
            provenance={
                "source_round": decision.source_round,
                "source_question": decision.source_question,
                "owner_answer": list(decision.authoritative_value),
                "recommendation_was": list(decision.provenance.recommendation_was),
            },
        )
        concept.trace_refs.append(
            self.trace.record(
                TraceAction.REGISTER_CONCEPT,
                "concept",
                concept_id,
                source_decisions=list(concept.source_decisions),
                canonical_name=canonical_name,
            )
        )
        self._current[concept_id] = concept
        return concept

    def revise(
        self,
        concept_id: str,
        *,
        version: str,
        definition: str,
        source_decision: Decision,
        unresolved: tuple[str, ...] = (),
    ) -> CoreConcept:
        """Create a traceable concept revision instead of editing history away."""

        current = self.get(concept_id)
        historical = replace(
            current,
            status=DecisionStatus.SUPERSEDED,
            trace_refs=list(current.trace_refs),
        )
        self._history.append(historical)
        revised = replace(
            current,
            version=version,
            definition=definition,
            status=source_decision.status,
            maturity=source_decision.status,
            source_decisions=tuple(
                dict.fromkeys((*current.source_decisions, source_decision.decision_id))
            ),
            unresolved=unresolved,
            supersedes=tuple(dict.fromkeys((*current.supersedes, f"{concept_id}@{current.version}"))),
            trace_refs=list(current.trace_refs),
        )
        revised.trace_refs.append(
            self.trace.record(
                TraceAction.REVISE_CONCEPT,
                "concept",
                concept_id,
                prior_version=current.version,
                version=version,
                source_decision=source_decision.decision_id,
            )
        )
        self._current[concept_id] = revised
        return revised
