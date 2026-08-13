"""Lightweight, inspectable provenance for design-flow state changes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .model import Decision, DecisionStatus, TraceAction, TraceRecord


class TraceLog:
    """Append-only in-memory TRACE with stable sequential identifiers."""

    def __init__(self) -> None:
        self._records: list[TraceRecord] = []

    def record(
        self,
        action: TraceAction,
        entity_type: str,
        entity_id: str,
        **details: Any,
    ) -> str:
        trace_id = f"trace-{len(self._records) + 1:04d}"
        self._records.append(
            TraceRecord(
                trace_id=trace_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=dict(details),
            )
        )
        return trace_id

    @property
    def records(self) -> tuple[TraceRecord, ...]:
        return tuple(self._records)

    def for_entity(self, entity_id: str) -> tuple[TraceRecord, ...]:
        return tuple(record for record in self._records if record.entity_id == entity_id)

    def get(self, trace_id: str) -> TraceRecord:
        for record in self._records:
            if record.trace_id == trace_id:
                return record
        raise ValueError(f"TRACE reference does not exist: {trace_id}")

    def validate_decision_synthesis(self, decision: Decision) -> TraceRecord:
        """Return the matching synthesis proof or reject fabricated provenance."""

        if decision.provenance.rule_source_value != decision.authoritative_value:
            raise ValueError(
                "Decision provenance is invalid: rule source does not match authoritative value"
            )
        failures: list[str] = []
        for trace_id in decision.trace_refs:
            try:
                record = self.get(trace_id)
            except ValueError as error:
                failures.append(str(error))
                continue
            if record.action is not TraceAction.SYNTHESIZE:
                failures.append(f"{trace_id} action is {record.action.value}, not SYNTHESIZE")
                continue
            if record.entity_type != "decision" or record.entity_id != decision.decision_id:
                failures.append(f"{trace_id} does not belong to decision {decision.decision_id}")
                continue
            expected = {
                "source_round": decision.source_round,
                "source_question": decision.source_question,
                "authoritative_value": list(decision.authoritative_value),
                "rule_source_value": list(decision.provenance.rule_source_value),
                "recommendation_was": list(decision.provenance.recommendation_was),
                "canonical_rule": decision.canonical_rule,
            }
            mismatch = next(
                (
                    key
                    for key, value in expected.items()
                    if record.details.get(key) != value
                ),
                None,
            )
            if mismatch is not None:
                failures.append(f"{trace_id} has mismatched {mismatch}")
                continue
            if decision.status in {DecisionStatus.SYNTHESIZED, DecisionStatus.UNRESOLVED}:
                if record.details.get("status") != decision.status.value:
                    failures.append(f"{trace_id} has mismatched status")
                    continue
            return record

        detail = "; ".join(failures) if failures else "no TRACE references supplied"
        raise ValueError(f"Decision provenance is invalid: {detail}")

    def validate_registered_decision(self, decision: Decision) -> TraceRecord:
        """Require both valid synthesis proof and an actual ledger-registration event."""

        synthesis = self.validate_decision_synthesis(decision)
        for trace_id in decision.trace_refs:
            try:
                record = self.get(trace_id)
            except ValueError:
                continue
            if (
                record.action is TraceAction.REGISTER_DECISION
                and record.entity_type == "decision"
                and record.entity_id == decision.decision_id
                and record.details.get("canonical_rule") == decision.canonical_rule
                and record.details.get("authoritative_value") == list(decision.authoritative_value)
                and record.details.get("source_round") == decision.source_round
                and record.details.get("source_question") == decision.source_question
            ):
                return synthesis
        raise ValueError(
            f"Decision provenance is invalid: {decision.decision_id} was not registered in the ledger"
        )

    def __iter__(self) -> Iterator[TraceRecord]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)
