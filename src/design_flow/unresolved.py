"""One canonical compiler for every unresolved-state surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .intake import DesignFlowWorkspace


def compile_unresolved_register(workspace: DesignFlowWorkspace) -> tuple[str, ...]:
    """Compile complete ordered unresolved state from committed authority."""

    state = workspace.state_compiler.compile(workspace.project, workspace.ledger)
    values: list[str] = [*state.unresolved]
    for design_round in workspace.rounds.rounds:
        values.extend(design_round.unresolved)
    for concept in (*workspace.concepts.concepts, *workspace.concepts.affected):
        values.extend(concept.unresolved)
    return tuple(dict.fromkeys(values))
