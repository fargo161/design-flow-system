"""Lightweight, inspectable provenance for design-flow state changes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .model import TraceAction, TraceRecord


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

    def __iter__(self) -> Iterator[TraceRecord]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)
