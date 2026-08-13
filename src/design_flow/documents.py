"""Living application document rendering and future compiler boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .concepts import CoreConceptRegistry
from .decisions import DecisionLedger
from .model import ApplicationBinding, CurrentDesignState, DecisionStatus, Project, TraceAction
from .trace import TraceLog


class DocumentCompiler(Protocol):
    """Reserved interface for later implementation/context/audit compilers."""

    def render(self) -> str: ...


class LivingApplicationDocumentRenderer:
    """Pure renderer using a generic, non-consequence-bearing binding scaffold."""

    schema_id = "design-flow.generic-application.v0.1.1"

    def __init__(self, trace: TraceLog) -> None:
        self.trace = trace

    def bindings_for(self, concepts: CoreConceptRegistry) -> tuple[ApplicationBinding, ...]:
        return tuple(
            ApplicationBinding(
                schema_id=self.schema_id,
                concept_id=concept.concept_id,
                section_key=f"concept:{concept.concept_id}",
            )
            for concept in concepts.concepts
        )

    def render(
        self,
        project: Project,
        current_state: CurrentDesignState,
        concepts: CoreConceptRegistry,
        ledger: DecisionLedger,
    ) -> str:
        document_id = f"{project.project_id}.LIVING_APPLICATION"
        lines = [
            f"# {project.name} — Living Application Document",
            "",
            "## Document Identity",
            "",
            f"- Document ID: `{document_id}`",
            f"- Version: `{current_state.version}`",
            "- Status: `FOUNDATIONAL`",
            f"- Scope: `{project.project_id}`",
            f"- Authority: {project.authority}",
            f"- Binding scaffold: `{self.schema_id}` (`FOUNDATIONAL`; not consequence-bearing)",
            "",
            "## System / Project Thesis",
            "",
            project.description,
            "",
            "## Current Core Concepts",
            "",
        ]

        if not concepts.concepts:
            lines.append("No core concepts are currently registered.")
            lines.append("")
        for concept in concepts.concepts:
            lines.extend(
                [
                    f"### {concept.canonical_name}",
                    "",
                    f"- Identity: `{concept.concept_id}`",
                    f"- Version: `{concept.version}`",
                    f"- Status: `{concept.status.value}`",
                    f"- Maturity: `{concept.maturity.value}`",
                    f"- Scope: `{concept.scope}`",
                    f"- Definition: {concept.definition}",
                    f"- Owns: {self._items(concept.owns)}",
                    f"- Does not own: {self._items(concept.does_not_own)}",
                    f"- Boundaries: {self._items(concept.boundaries)}",
                    f"- Dependencies: {self._items(concept.dependencies)}",
                    f"- Relations: {self._items(concept.relations)}",
                    f"- Source decisions: {self._code_items(concept.source_decisions)}",
                    f"- Unresolved: {self._items(concept.unresolved)}",
                    f"- Supersedes: {self._code_items(concept.supersedes)}",
                    f"- Current provenance: {self._concept_provenance(concept.provenance)}",
                    f"- TRACE: {self._code_items(tuple(concept.trace_refs))}",
                    "",
                ]
            )

        lines.extend(["## Current Decisions", ""])
        if not current_state.decisions:
            lines.extend(["No operative decisions are currently registered.", ""])
        for decision in current_state.decisions:
            lines.extend(
                [
                    f"### {decision.decision_id}",
                    "",
                    f"- Rule: {decision.canonical_rule}",
                    f"- Authoritative owner value: `{self._joined(decision.authoritative_value)}`",
                    f"- Status: `{decision.status.value}`",
                    f"- Scope: `{decision.scope}`",
                    f"- Source: round `{decision.source_round}`, question `{decision.source_question}`",
                    f"- Source question: {decision.provenance.question_text}",
                    f"- Options: {self._option_items(decision.provenance.options)}",
                    f"- Historical recommendation: `{self._joined(decision.provenance.recommendation_was)}`",
                    f"- Recommendation reason: {decision.provenance.recommendation_reason}",
                    f"- TRACE: {self._code_items(tuple(decision.trace_refs))}",
                    "",
                ]
            )

        concept_unresolved = [
            item
            for concept in (*concepts.concepts, *concepts.affected)
            for item in concept.unresolved
        ]
        unresolved = tuple(dict.fromkeys((*current_state.unresolved, *concept_unresolved)))
        lines.extend(["## Unresolved Register", ""])
        lines.extend(self._bullet_block(unresolved, "No unresolved items are currently registered."))

        lines.extend(["## Affected / Unresolved Concepts", ""])
        if not concepts.affected:
            lines.extend(["No affected concepts await owner resolution.", ""])
        for concept in concepts.affected:
            lines.extend(
                [
                    f"- `{concept.concept_id}@{concept.version}` — status `{concept.status.value}`; "
                    f"maturity `{concept.maturity.value}`; {self._items(concept.unresolved)}",
                ]
            )
        if concepts.affected:
            lines.append("")

        superseded = tuple(
            decision for decision in ledger.decisions if decision.status is DecisionStatus.SUPERSEDED
        )
        lines.extend(["## Superseded / Historical State", ""])
        if not superseded and not concepts.history:
            lines.extend(["No superseded state is currently registered.", ""])
        for decision in superseded:
            lines.extend(
                [
                    f"- `{decision.decision_id}` — {decision.canonical_rule} "
                    f"(status `{decision.status.value}`; TRACE {self._code_items(tuple(decision.trace_refs))})",
                ]
            )
        for concept in concepts.history:
            source = concept.provenance.get("current_source", {})
            lines.append(
                f"- `{concept.concept_id}@{concept.version}` — {concept.definition} "
                f"(status `{concept.status.value}`; source decision "
                f"`{source.get('source_decision') if isinstance(source, Mapping) else 'UNKNOWN'}`; "
                f"TRACE `{source.get('trace_ref') if isinstance(source, Mapping) else 'UNKNOWN'}`)"
            )
        if superseded or concepts.history:
            lines.append("")

        lines.extend(["## TRACE / Recent Changes", ""])
        for record in self.trace.records:
            lines.append(
                f"- `{record.trace_id}` `{record.action.value}` "
                f"{record.entity_type} `{record.entity_id}` — {self._details(record.details)}"
            )
        lines.append("")
        return "\n".join(lines)

    def record_generation(self, project: Project, current_state: CurrentDesignState) -> str:
        """Explicitly record generation without coupling mutation to rendering."""

        return self.trace.record(
            TraceAction.GENERATE_DOCUMENT,
            "document",
            f"{project.project_id}.LIVING_APPLICATION",
            version=current_state.version,
            schema_id=self.schema_id,
        )

    @staticmethod
    def _joined(items: object) -> str:
        if isinstance(items, (tuple, list)):
            return " + ".join(str(item) for item in items) or "NONE"
        return str(items)

    @staticmethod
    def _items(items: tuple[str, ...]) -> str:
        return "; ".join(items) if items else "None registered"

    @staticmethod
    def _code_items(items: tuple[str, ...]) -> str:
        return ", ".join(f"`{item}`" for item in items) if items else "None registered"

    @staticmethod
    def _option_items(items: tuple[object, ...]) -> str:
        return "; ".join(
            f"`{getattr(item, 'key')}` {getattr(item, 'label')}" for item in items
        ) if items else "None registered"

    @classmethod
    def _concept_provenance(cls, provenance: Mapping[str, object]) -> str:
        source = provenance.get("current_source", {})
        if not isinstance(source, Mapping):
            return "invalid provenance shape"
        return (
            f"decision `{source.get('source_decision')}`, "
            f"round `{source.get('source_round')}`, "
            f"question `{source.get('source_question')}`, "
            f"owner answer `{cls._joined(source.get('owner_answer', []))}`, "
            f"recommendation was `{cls._joined(source.get('recommendation_was', []))}`, "
            f"TRACE `{source.get('trace_ref')}`"
        )

    @staticmethod
    def _bullet_block(items: tuple[str, ...], empty: str) -> list[str]:
        if not items:
            return [empty, ""]
        return [*(f"- {item}" for item in items), ""]

    @staticmethod
    def _details(details: Mapping[str, object]) -> str:
        if not details:
            return "No additional details."
        return "; ".join(f"{key}={value!r}" for key, value in sorted(details.items()))
