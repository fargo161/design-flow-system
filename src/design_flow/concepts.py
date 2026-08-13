"""PSG-informed concept registration and supersession-safe lifecycle handling."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from .model import (
    ConceptMaturity,
    ConceptStatus,
    CoreConcept,
    Decision,
    DecisionStatus,
    TraceAction,
)
from .trace import TraceLog


class CoreConceptRegistry:
    """Separate settled current, affected/unresolved, and historical concepts."""

    def __init__(self, trace: TraceLog) -> None:
        self.trace = trace
        self._current: dict[str, CoreConcept] = {}
        self._affected: dict[str, CoreConcept] = {}
        self._history: list[CoreConcept] = []

    @property
    def concepts(self) -> tuple[CoreConcept, ...]:
        """Settled current concepts only; affected concepts never masquerade here."""

        return tuple(self._current.values())

    @property
    def affected(self) -> tuple[CoreConcept, ...]:
        return tuple(self._affected.values())

    @property
    def history(self) -> tuple[CoreConcept, ...]:
        return tuple(self._history)

    def get(self, concept_id: str) -> CoreConcept:
        if concept_id in self._current:
            return self._current[concept_id]
        if concept_id in self._affected:
            return self._affected[concept_id]
        raise KeyError(f"Unknown current or affected concept: {concept_id}")

    def register_from_decision(
        self,
        decision: Decision,
        *,
        concept_id: str,
        canonical_name: str,
        definition: str,
        maturity: ConceptMaturity = ConceptMaturity.DEFINED,
        owns: tuple[str, ...] = (),
        does_not_own: tuple[str, ...] = (),
        boundaries: tuple[str, ...] = (),
        dependencies: tuple[str, ...] = (),
        relations: tuple[str, ...] = (),
        unresolved: tuple[str, ...] = (),
    ) -> CoreConcept:
        if concept_id in self._current or concept_id in self._affected:
            raise ValueError(f"Concept already exists: {concept_id}")
        self._validate_source_decision(decision)

        status = (
            ConceptStatus.UNRESOLVED
            if decision.status is DecisionStatus.UNRESOLVED or unresolved
            else ConceptStatus.CURRENT
        )
        concept = CoreConcept(
            concept_id=concept_id,
            canonical_name=canonical_name,
            version="0.1.1",
            status=status,
            maturity=maturity,
            scope=decision.scope,
            definition=definition,
            owns=owns,
            does_not_own=does_not_own,
            boundaries=boundaries,
            dependencies=dependencies,
            relations=relations,
            source_decisions=(decision.decision_id,),
            unresolved=tuple(dict.fromkeys((*unresolved, *decision.unresolved_consequences))),
            provenance=self._initial_provenance(decision),
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
        target = self._affected if status is ConceptStatus.UNRESOLVED else self._current
        target[concept_id] = concept
        return concept

    def mark_affected_by_supersession(self, earlier: Decision, later: Decision) -> tuple[str, ...]:
        """Conservatively quarantine concepts whose source decision was replaced."""

        affected_ids: list[str] = []
        for concept_id, concept in tuple(self._current.items()):
            if earlier.decision_id not in concept.source_decisions:
                continue
            reason = (
                f"Concept {concept_id} requires explicit resolution because source decision "
                f"{earlier.decision_id} was superseded by {later.decision_id}."
            )
            concept.status = ConceptStatus.UNRESOLVED
            concept.unresolved = tuple(dict.fromkeys((*concept.unresolved, reason)))
            concept.trace_refs.append(
                self.trace.record(
                    TraceAction.MARK_CONCEPT_AFFECTED,
                    "concept",
                    concept_id,
                    superseded_decision=earlier.decision_id,
                    replacement_decision=later.decision_id,
                    resolution_required=True,
                )
            )
            del self._current[concept_id]
            self._affected[concept_id] = concept
            affected_ids.append(concept_id)
        return tuple(affected_ids)

    def mark_unresolved(self, concept_id: str, *, reason: str) -> CoreConcept:
        concept = self.get(concept_id)
        if concept_id in self._current:
            del self._current[concept_id]
            self._affected[concept_id] = concept
        concept.status = ConceptStatus.UNRESOLVED
        concept.unresolved = tuple(dict.fromkeys((*concept.unresolved, reason)))
        concept.trace_refs.append(
            self.trace.record(
                TraceAction.MARK_CONCEPT_AFFECTED,
                "concept",
                concept_id,
                reason=reason,
                resolution_required=True,
            )
        )
        return concept

    def revise(
        self,
        concept_id: str,
        *,
        version: str,
        definition: str,
        source_decision: Decision,
        maturity: ConceptMaturity = ConceptMaturity.DEFINED,
        unresolved: tuple[str, ...] = (),
    ) -> CoreConcept:
        """Resolve a concept with a new version and explicit provenance lineage."""

        self._validate_source_decision(source_decision)
        prior = self.get(concept_id)
        historical = replace(
            prior,
            status=ConceptStatus.SUPERSEDED,
            provenance=deepcopy(prior.provenance),
            trace_refs=list(prior.trace_refs),
        )
        self._history.append(historical)

        source = self._source_provenance(source_decision)
        provenance = deepcopy(prior.provenance)
        provenance["current_source"] = source
        provenance.setdefault("revisions", []).append(
            {
                "prior_version": prior.version,
                "version": version,
                **source,
            }
        )
        status = ConceptStatus.UNRESOLVED if unresolved else ConceptStatus.CURRENT
        revised = replace(
            prior,
            version=version,
            definition=definition,
            status=status,
            maturity=maturity,
            source_decisions=tuple(
                dict.fromkeys((*prior.source_decisions, source_decision.decision_id))
            ),
            unresolved=unresolved,
            supersedes=tuple(
                dict.fromkeys((*prior.supersedes, f"{concept_id}@{prior.version}"))
            ),
            provenance=provenance,
            trace_refs=list(prior.trace_refs),
        )
        revised.trace_refs.append(
            self.trace.record(
                TraceAction.REVISE_CONCEPT,
                "concept",
                concept_id,
                prior_version=prior.version,
                version=version,
                source_decision=source_decision.decision_id,
                source_trace=source["trace_ref"],
            )
        )
        self._current.pop(concept_id, None)
        self._affected.pop(concept_id, None)
        target = self._affected if status is ConceptStatus.UNRESOLVED else self._current
        target[concept_id] = revised
        return revised

    def deprecate(self, concept_id: str, *, reason: str) -> CoreConcept:
        """Resolve an affected concept by moving it into historical state."""

        concept = self.get(concept_id)
        historical = replace(
            concept,
            status=ConceptStatus.DEPRECATED,
            maturity=ConceptMaturity.DEPRECATED,
            unresolved=tuple(dict.fromkeys((*concept.unresolved, reason))),
            provenance=deepcopy(concept.provenance),
            trace_refs=list(concept.trace_refs),
        )
        historical.trace_refs.append(
            self.trace.record(
                TraceAction.DEPRECATE_CONCEPT,
                "concept",
                concept_id,
                version=concept.version,
                reason=reason,
            )
        )
        self._current.pop(concept_id, None)
        self._affected.pop(concept_id, None)
        self._history.append(historical)
        return historical

    def _validate_source_decision(self, decision: Decision) -> None:
        if decision.status not in {
            DecisionStatus.SYNTHESIZED,
            DecisionStatus.TESTED,
            DecisionStatus.RATIFIED,
            DecisionStatus.UNRESOLVED,
        }:
            raise ValueError("Concepts require a current synthesized or unresolved decision")
        self.trace.validate_registered_decision(decision)

    def _initial_provenance(self, decision: Decision) -> dict[str, object]:
        source = self._source_provenance(decision)
        return {
            "original_source": deepcopy(source),
            "current_source": deepcopy(source),
            "revisions": [],
        }

    def _source_provenance(self, decision: Decision) -> dict[str, object]:
        record = self.trace.validate_registered_decision(decision)
        return {
            "source_decision": decision.decision_id,
            "source_round": decision.source_round,
            "source_question": decision.source_question,
            "owner_answer": list(decision.authoritative_value),
            "recommendation_was": list(decision.provenance.recommendation_was),
            "trace_ref": record.trace_id,
        }
