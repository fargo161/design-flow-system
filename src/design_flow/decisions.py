"""Decision synthesis, ledger history, conflict seams, and current state."""

from __future__ import annotations

from collections.abc import Callable

from .model import (
    ConflictRecord,
    ConflictRelation,
    CurrentDesignState,
    Decision,
    DecisionProvenance,
    DecisionStatus,
    DesignRound,
    OwnerAnswer,
    Project,
    TraceAction,
)
from .trace import TraceLog


RuleBuilder = Callable[[OwnerAnswer], str]


class DecisionSynthesizer:
    """Translate an owner answer into a rule while retaining the advice."""

    def __init__(self, trace: TraceLog) -> None:
        self.trace = trace

    def synthesize(
        self,
        design_round: DesignRound,
        question_id: str,
        *,
        decision_id: str,
        scope: str,
        rule_builder: RuleBuilder,
        dependencies: tuple[str, ...] = (),
        unresolved_consequences: tuple[str, ...] = (),
    ) -> Decision:
        question = design_round.question(question_id)
        if question.owner_answer is None:
            raise ValueError("A decision cannot be synthesized before the owner answers")

        answer = question.owner_answer
        canonical_rule = rule_builder(answer).strip()
        if not canonical_rule:
            raise ValueError("Synthesis must produce a non-empty canonical rule")

        status = (
            DecisionStatus.UNRESOLVED
            if answer.status is DecisionStatus.UNRESOLVED
            else DecisionStatus.SYNTHESIZED
        )
        consequences = list(unresolved_consequences)
        if status is DecisionStatus.UNRESOLVED:
            consequences.extend(question.derived_implications)

        provenance = DecisionProvenance(
            recommendation_was=question.recommendation.proposed_answer,
            recommendation_reason=question.recommendation.reason,
            owner_raw_value=answer.raw_value,
            owner_normalized_value=answer.normalized_value,
            owner_qualifiers=answer.qualifiers,
            question_text=question.text,
            options=question.options,
        )
        decision = Decision(
            decision_id=decision_id,
            canonical_rule=canonical_rule,
            authoritative_value=answer.normalized_value,
            status=status,
            scope=scope,
            source_round=design_round.round_id,
            source_question=question.question_id,
            provenance=provenance,
            dependencies=dependencies,
            unresolved_consequences=tuple(dict.fromkeys(consequences)),
        )
        trace_id = self.trace.record(
            TraceAction.SYNTHESIZE,
            "decision",
            decision_id,
            source_round=design_round.round_id,
            source_question=question.question_id,
            authoritative_value=list(answer.normalized_value),
            recommendation_was=list(question.recommendation.proposed_answer),
            status=status.value,
        )
        decision.trace_refs.append(trace_id)
        design_round.synthesis.append(canonical_rule)
        design_round.derived_rules.append(canonical_rule)
        return decision


class DecisionLedger:
    """Append-preserving history and explicit decision relationships."""

    def __init__(self, trace: TraceLog) -> None:
        self.trace = trace
        self._decisions: dict[str, Decision] = {}
        self._relationships: list[ConflictRecord] = []

    @property
    def decisions(self) -> tuple[Decision, ...]:
        return tuple(self._decisions.values())

    @property
    def relationships(self) -> tuple[ConflictRecord, ...]:
        return tuple(self._relationships)

    def get(self, decision_id: str) -> Decision:
        try:
            return self._decisions[decision_id]
        except KeyError as error:
            raise KeyError(f"Unknown decision: {decision_id}") from error

    def register(self, decision: Decision) -> Decision:
        if decision.decision_id in self._decisions:
            raise ValueError(f"Decision already exists: {decision.decision_id}")
        if not decision.trace_refs:
            raise ValueError("Authoritative decisions require synthesis provenance")
        self._decisions[decision.decision_id] = decision
        decision.trace_refs.append(
            self.trace.record(
                TraceAction.REGISTER_DECISION,
                "decision",
                decision.decision_id,
                canonical_rule=decision.canonical_rule,
                authoritative_value=list(decision.authoritative_value),
                source_round=decision.source_round,
                source_question=decision.source_question,
            )
        )
        return decision

    def record_relationship(
        self,
        earlier_decision: str,
        later_decision: str,
        relation: ConflictRelation,
        notes: str,
    ) -> ConflictRecord:
        self.get(earlier_decision)
        self.get(later_decision)
        record = ConflictRecord(
            earlier_decision=earlier_decision,
            later_decision=later_decision,
            relation=relation,
            notes=notes,
        )
        self._relationships.append(record)
        return record

    def supersede(self, earlier_decision: str, later_decision: str, *, notes: str) -> None:
        earlier = self.get(earlier_decision)
        later = self.get(later_decision)
        if earlier.status is DecisionStatus.SUPERSEDED:
            raise ValueError(f"Decision is already superseded: {earlier_decision}")
        earlier.status = DecisionStatus.SUPERSEDED
        later.supersedes = tuple(dict.fromkeys((*later.supersedes, earlier_decision)))
        self.record_relationship(
            earlier_decision,
            later_decision,
            ConflictRelation.SUPERSEDES,
            notes,
        )
        trace_id = self.trace.record(
            TraceAction.SUPERSEDE,
            "decision",
            earlier_decision,
            replaced_by=later_decision,
            notes=notes,
        )
        earlier.trace_refs.append(trace_id)
        later.trace_refs.append(trace_id)


class CurrentStateCompiler:
    """Compile operative rules without discarding ledger history."""

    def compile(self, project: Project, ledger: DecisionLedger) -> CurrentDesignState:
        active = tuple(
            decision
            for decision in ledger.decisions
            if decision.status is not DecisionStatus.SUPERSEDED
        )
        for decision in active:
            if not decision.trace_refs:
                raise ValueError(f"Decision lacks provenance: {decision.decision_id}")

        unresolved: list[str] = list(project.unresolved_areas)
        for decision in active:
            unresolved.extend(decision.unresolved_consequences)
            if decision.status is DecisionStatus.UNRESOLVED and not decision.unresolved_consequences:
                unresolved.append(f"Resolve decision {decision.decision_id}.")

        return CurrentDesignState(
            project_id=project.project_id,
            version=project.current_state_version,
            decisions=active,
            unresolved=tuple(dict.fromkeys(unresolved)),
        )
