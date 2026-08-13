"""Optional proposal-only LLM seam with no provider dependency."""

from __future__ import annotations

from typing import Protocol

from .session import DraftRound


class LLMAdapter(Protocol):
    """An adapter may propose a draft, never activate semantic state."""

    def propose_round(self, context_handoff: str) -> DraftRound: ...


class LLMUnavailableError(RuntimeError):
    """Raised only when proposal generation is requested without an adapter."""


def request_draft(adapter: LLMAdapter | None, context_handoff: str) -> DraftRound:
    if adapter is None:
        raise LLMUnavailableError(
            "No LLM adapter is configured; manual deterministic operation remains available"
        )
    draft = adapter.propose_round(context_handoff)
    if not isinstance(draft, DraftRound):
        raise TypeError("LLM adapters must return a non-authoritative DraftRound")
    return draft
