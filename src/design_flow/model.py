"""Core semantic records for the Design Flow System.

The records in this module deliberately keep recommendations, owner answers,
derived decisions, concepts, and rendered documents as distinct layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def freeze_semantic_value(value: Any) -> Any:
    """Snapshot admitted semantic values or reject unsafe mutable aliases."""

    return _freeze_semantic_value(value, active_containers=set())


def _freeze_semantic_value(value: Any, *, active_containers: set[int]) -> Any:
    if isinstance(value, Enum):
        return _freeze_semantic_value(value.value, active_containers=active_containers)
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, Mapping):
        return _freeze_mapping(value, active_containers=active_containers)
    if isinstance(value, (list, tuple)):
        return _freeze_sequence(value, active_containers=active_containers)
    if isinstance(value, (set, frozenset)):
        return _freeze_set(value, active_containers=active_containers)
    raise TypeError(
        f"Unsupported semantic value type: {type(value).__module__}.{type(value).__qualname__}"
    )


def _enter_container(value: Any, active_containers: set[int]) -> int:
    identity = id(value)
    if identity in active_containers:
        raise TypeError("Cyclic semantic containers are not supported")
    active_containers.add(identity)
    return identity


def _freeze_mapping(value: Mapping[Any, Any], *, active_containers: set[int]) -> Mapping[Any, Any]:
    identity = _enter_container(value, active_containers)
    try:
        frozen: dict[Any, Any] = {}
        for key, item in value.items():
            frozen_key = _freeze_semantic_value(key, active_containers=active_containers)
            try:
                hash(frozen_key)
            except TypeError as error:
                raise TypeError("Semantic mapping keys must freeze to hashable values") from error
            frozen[frozen_key] = _freeze_semantic_value(
                item, active_containers=active_containers
            )
        return MappingProxyType(frozen)
    finally:
        active_containers.remove(identity)


def _freeze_sequence(value: list[Any] | tuple[Any, ...], *, active_containers: set[int]) -> tuple[Any, ...]:
    identity = _enter_container(value, active_containers)
    try:
        return tuple(
            _freeze_semantic_value(item, active_containers=active_containers)
            for item in value
        )
    finally:
        active_containers.remove(identity)


def _freeze_set(value: set[Any] | frozenset[Any], *, active_containers: set[int]) -> frozenset[Any]:
    identity = _enter_container(value, active_containers)
    try:
        return frozenset(
            _freeze_semantic_value(item, active_containers=active_containers)
            for item in value
        )
    finally:
        active_containers.remove(identity)


class DesignFlowMode(StrEnum):
    """The intent that guides future round selection."""

    DISCOVERY = "DISCOVERY"
    REFINEMENT = "REFINEMENT"
    REPAIR = "REPAIR"


class QuestionType(StrEnum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    YES_NO = "YES_NO"


class DecisionStatus(StrEnum):
    OPEN = "OPEN"
    PROPOSED = "PROPOSED"
    OWNER_SELECTED = "OWNER_SELECTED"
    SYNTHESIZED = "SYNTHESIZED"
    TESTED = "TESTED"
    RATIFIED = "RATIFIED"
    UNRESOLVED = "UNRESOLVED"
    SUPERSEDED = "SUPERSEDED"


class ConceptStatus(StrEnum):
    """Whether a concept is operative, affected, or historical."""

    CURRENT = "CURRENT"
    UNRESOLVED = "UNRESOLVED"
    DEPRECATED = "DEPRECATED"
    SUPERSEDED = "SUPERSEDED"


class ConceptMaturity(StrEnum):
    """How well established a concept is, independent of its status."""

    PROPOSED = "PROPOSED"
    DEFINED = "DEFINED"
    TESTED = "TESTED"
    STABLE = "STABLE"
    DISPUTED = "DISPUTED"
    DEPRECATED = "DEPRECATED"


class ConflictRelation(StrEnum):
    COMPATIBLE = "compatible"
    POTENTIAL_CONFLICT = "potential_conflict"
    SUPERSEDES = "supersedes"
    UNRESOLVED_CONFLICT = "unresolved_conflict"


class TraceAction(StrEnum):
    REGISTER_PROJECT = "REGISTER_PROJECT"
    REGISTER_ROUND = "REGISTER_ROUND"
    REGISTER_QUESTION = "REGISTER_QUESTION"
    RECOMMEND = "RECOMMEND"
    OWNER_SELECT = "OWNER_SELECT"
    SYNTHESIZE = "SYNTHESIZE"
    REGISTER_DECISION = "REGISTER_DECISION"
    MARK_UNRESOLVED = "MARK_UNRESOLVED"
    SUPERSEDE = "SUPERSEDE"
    REGISTER_CONCEPT = "REGISTER_CONCEPT"
    MARK_CONCEPT_AFFECTED = "MARK_CONCEPT_AFFECTED"
    REVISE_CONCEPT = "REVISE_CONCEPT"
    DEPRECATE_CONCEPT = "DEPRECATE_CONCEPT"
    GENERATE_DOCUMENT = "GENERATE_DOCUMENT"


@dataclass(slots=True, frozen=True)
class QuestionOption:
    key: str
    label: str

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Question option keys cannot be empty")
        if not self.label.strip():
            raise ValueError("Question option labels cannot be empty")


@dataclass(slots=True, frozen=True)
class Recommendation:
    """Advisory input; never a substitute for an owner answer."""

    proposed_answer: tuple[str, ...]
    reason: str
    status: DecisionStatus = DecisionStatus.PROPOSED

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposed_answer", tuple(self.proposed_answer))


@dataclass(slots=True, frozen=True)
class OwnerAnswer:
    raw_value: str
    normalized_value: tuple[str, ...]
    qualifiers: tuple[str, ...]
    status: DecisionStatus
    source_round: str
    source_question: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_value", tuple(self.normalized_value))
        object.__setattr__(self, "qualifiers", tuple(self.qualifiers))

    @property
    def qualifier(self) -> str | None:
        return "; ".join(self.qualifiers) if self.qualifiers else None


@dataclass(slots=True, frozen=True)
class Question:
    question_id: str
    text: str
    question_type: QuestionType
    options: tuple[QuestionOption, ...]
    recommendation: Recommendation
    owner_answer: OwnerAnswer | None = None
    answer_status: DecisionStatus = DecisionStatus.PROPOSED
    derived_implications: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", tuple(self.options))
        object.__setattr__(self, "derived_implications", tuple(self.derived_implications))
        object.__setattr__(self, "trace_refs", tuple(self.trace_refs))
        keys = [option.key.upper() for option in self.options]
        if not self.question_id.strip() or not self.text.strip():
            raise ValueError("Questions require an id and text")
        if len(keys) < 2 or len(set(keys)) != len(keys):
            raise ValueError("Questions require at least two uniquely keyed options")
        proposed = {value.upper() for value in self.recommendation.proposed_answer}
        if proposed and not proposed.issubset(set(keys)):
            raise ValueError("Recommendation must refer to a declared option")

    @property
    def option_keys(self) -> tuple[str, ...]:
        return tuple(option.key.upper() for option in self.options)


@dataclass(slots=True, frozen=True)
class DesignRound:
    round_id: str
    topic: str
    purpose: str
    prerequisites: tuple[str, ...] = ()
    questions: tuple[Question, ...] = ()
    owner_answer_set: Mapping[str, OwnerAnswer] = field(default_factory=dict)
    synthesis: tuple[str, ...] = ()
    derived_rules: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    conflicts_detected: tuple[str, ...] = ()
    status: DecisionStatus = DecisionStatus.OPEN
    trace_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "prerequisites",
            "questions",
            "synthesis",
            "derived_rules",
            "unresolved",
            "conflicts_detected",
            "trace_refs",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        object.__setattr__(
            self, "owner_answer_set", MappingProxyType(dict(self.owner_answer_set))
        )

    def question(self, question_id: str) -> Question:
        for item in self.questions:
            if item.question_id == question_id:
                return item
        raise KeyError(f"Unknown question: {question_id}")


@dataclass(slots=True, frozen=True)
class Project:
    project_id: str
    name: str
    description: str
    current_mode: DesignFlowMode
    authority: str
    current_state_version: str = "0.2.0"
    source_context: tuple[str, ...] = ()
    unresolved_areas: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_context", tuple(self.source_context))
        object.__setattr__(self, "unresolved_areas", tuple(self.unresolved_areas))


@dataclass(slots=True, frozen=True)
class DecisionProvenance:
    recommendation_was: tuple[str, ...]
    recommendation_reason: str
    owner_raw_value: str
    owner_normalized_value: tuple[str, ...]
    owner_qualifiers: tuple[str, ...]
    question_text: str = ""
    options: tuple[QuestionOption, ...] = ()
    rule_source_value: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "recommendation_was",
            "owner_normalized_value",
            "owner_qualifiers",
            "options",
            "rule_source_value",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for field_name in (
            "recommendation_reason",
            "owner_raw_value",
            "question_text",
        ):
            if type(getattr(self, field_name)) is not str:
                raise TypeError(f"Decision provenance {field_name} must be a string")
        for field_name in (
            "recommendation_was",
            "owner_normalized_value",
            "owner_qualifiers",
            "rule_source_value",
        ):
            if any(type(item) is not str for item in getattr(self, field_name)):
                raise TypeError(f"Decision provenance {field_name} must contain only strings")
        if any(not isinstance(item, QuestionOption) for item in self.options):
            raise TypeError("Decision provenance options must contain QuestionOption records")


@dataclass(slots=True, frozen=True)
class Decision:
    """Immutable authoritative decision snapshot owned by the decision ledger."""

    decision_id: str
    canonical_rule: str
    authoritative_value: tuple[str, ...]
    status: DecisionStatus
    scope: str
    source_round: str
    source_question: str
    provenance: DecisionProvenance
    dependencies: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    unresolved_consequences: tuple[str, ...] = ()
    trace_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "authoritative_value",
            "dependencies",
            "supersedes",
            "unresolved_consequences",
            "trace_refs",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        for field_name in (
            "decision_id",
            "canonical_rule",
            "scope",
            "source_round",
            "source_question",
        ):
            if type(getattr(self, field_name)) is not str:
                raise TypeError(f"Decision {field_name} must be a string")
        for field_name in (
            "authoritative_value",
            "dependencies",
            "supersedes",
            "unresolved_consequences",
            "trace_refs",
        ):
            if any(type(item) is not str for item in getattr(self, field_name)):
                raise TypeError(f"Decision {field_name} must contain only strings")
        if not isinstance(self.status, DecisionStatus):
            raise TypeError("Decision status must be a DecisionStatus")
        if not isinstance(self.provenance, DecisionProvenance):
            raise TypeError("Decision provenance must be a DecisionProvenance record")


@dataclass(slots=True, frozen=True)
class ConflictRecord:
    earlier_decision: str
    later_decision: str
    relation: ConflictRelation
    notes: str


@dataclass(slots=True, frozen=True)
class TraceRecord:
    trace_id: str
    action: TraceAction
    entity_type: str
    entity_id: str
    details: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class CoreConcept:
    concept_id: str
    canonical_name: str
    version: str
    status: ConceptStatus
    maturity: ConceptMaturity
    scope: str
    definition: str
    owns: tuple[str, ...] = ()
    does_not_own: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    source_decisions: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    trace_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "owns",
            "does_not_own",
            "boundaries",
            "dependencies",
            "relations",
            "source_decisions",
            "unresolved",
            "supersedes",
            "trace_refs",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        object.__setattr__(self, "provenance", freeze_semantic_value(self.provenance))


@dataclass(slots=True, frozen=True)
class CurrentDesignState:
    project_id: str
    version: str
    decisions: tuple[Decision, ...]
    unresolved: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class ApplicationBinding:
    """Non-consequence-bearing scaffold for a future binding layer."""

    schema_id: str
    concept_id: str
    section_key: str
