"""Strict plain-data codecs for the v0.2 persistence boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import Enum
from typing import Any, TypeVar

from .model import (
    ConceptMaturity,
    ConceptStatus,
    ConflictRecord,
    ConflictRelation,
    CoreConcept,
    Decision,
    DecisionProvenance,
    DecisionStatus,
    DesignFlowMode,
    DesignRound,
    OwnerAnswer,
    Project,
    Question,
    QuestionOption,
    QuestionType,
    Recommendation,
    TraceAction,
    TraceRecord,
    freeze_semantic_value,
)


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
EnumT = TypeVar("EnumT", bound=Enum)


class SchemaError(ValueError):
    """A persisted plain-data value does not match its declared schema."""


def to_plain(value: Any) -> JsonValue:
    """Convert admitted immutable domain data into deterministic JSON data."""

    if isinstance(value, Enum):
        return to_plain(value.value)
    if value is None or type(value) in (bool, int, float, str):
        return value
    if isinstance(value, Mapping):
        plain: dict[str, JsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("Persisted object keys must be strings")
            plain[key] = to_plain(item)
        return plain
    if isinstance(value, (list, tuple)):
        return [to_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [to_plain(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    raise TypeError(f"Cannot serialize {type(value).__module__}.{type(value).__qualname__}")


def strict_object(
    value: Any,
    fields: set[str],
    context: str,
    *,
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise SchemaError(f"{context} must be an object")
    optional = optional or set()
    unknown = set(value) - fields
    missing = (fields - optional) - set(value)
    if unknown:
        raise SchemaError(f"{context} has unknown fields: {', '.join(sorted(unknown))}")
    if missing:
        raise SchemaError(f"{context} is missing fields: {', '.join(sorted(missing))}")
    return value


def as_string(value: Any, context: str) -> str:
    if type(value) is not str:
        raise SchemaError(f"{context} must be a string")
    return value


def as_int(value: Any, context: str) -> int:
    if type(value) is not int:
        raise SchemaError(f"{context} must be an integer")
    return value


def as_bool(value: Any, context: str) -> bool:
    if type(value) is not bool:
        raise SchemaError(f"{context} must be a boolean")
    return value


def as_list(value: Any, context: str) -> list[Any]:
    if type(value) is not list:
        raise SchemaError(f"{context} must be an array")
    return value


def string_tuple(value: Any, context: str) -> tuple[str, ...]:
    return tuple(as_string(item, f"{context}[]") for item in as_list(value, context))


def enum_value(enum_type: type[EnumT], value: Any, context: str) -> EnumT:
    raw = as_string(value, context)
    try:
        return enum_type(raw)
    except ValueError as error:
        raise SchemaError(f"{context} has unsupported value: {raw}") from error


def encode_project(project: Project) -> dict[str, JsonValue]:
    return {
        "name": project.name,
        "description": project.description,
        "mode": project.current_mode.value,
        "authority": project.authority,
        "current_state_version": project.current_state_version,
        "source_context": list(project.source_context),
        "unresolved_areas": list(project.unresolved_areas),
    }


def decode_project(project_id: str, value: Any) -> Project:
    data = strict_object(
        value,
        {
            "name",
            "description",
            "mode",
            "authority",
            "current_state_version",
            "source_context",
            "unresolved_areas",
        },
        "manifest.project",
    )
    return Project(
        project_id=project_id,
        name=as_string(data["name"], "manifest.project.name"),
        description=as_string(data["description"], "manifest.project.description"),
        current_mode=enum_value(DesignFlowMode, data["mode"], "manifest.project.mode"),
        authority=as_string(data["authority"], "manifest.project.authority"),
        current_state_version=as_string(
            data["current_state_version"], "manifest.project.current_state_version"
        ),
        source_context=string_tuple(data["source_context"], "manifest.project.source_context"),
        unresolved_areas=string_tuple(
            data["unresolved_areas"], "manifest.project.unresolved_areas"
        ),
    )


def encode_option(option: QuestionOption) -> dict[str, JsonValue]:
    return {"key": option.key, "label": option.label}


def decode_option(value: Any, context: str) -> QuestionOption:
    data = strict_object(value, {"key", "label"}, context)
    return QuestionOption(
        as_string(data["key"], f"{context}.key"),
        as_string(data["label"], f"{context}.label"),
    )


def encode_recommendation(value: Recommendation) -> dict[str, JsonValue]:
    return {
        "proposed_answer": list(value.proposed_answer),
        "reason": value.reason,
        "status": value.status.value,
    }


def decode_recommendation(value: Any, context: str) -> Recommendation:
    data = strict_object(value, {"proposed_answer", "reason", "status"}, context)
    return Recommendation(
        proposed_answer=string_tuple(data["proposed_answer"], f"{context}.proposed_answer"),
        reason=as_string(data["reason"], f"{context}.reason"),
        status=enum_value(DecisionStatus, data["status"], f"{context}.status"),
    )


def encode_owner_answer(value: OwnerAnswer) -> dict[str, JsonValue]:
    return {
        "raw_value": value.raw_value,
        "normalized_value": list(value.normalized_value),
        "qualifiers": list(value.qualifiers),
        "status": value.status.value,
        "source_round": value.source_round,
        "source_question": value.source_question,
    }


def decode_owner_answer(value: Any, context: str) -> OwnerAnswer:
    data = strict_object(
        value,
        {
            "raw_value",
            "normalized_value",
            "qualifiers",
            "status",
            "source_round",
            "source_question",
        },
        context,
    )
    return OwnerAnswer(
        raw_value=as_string(data["raw_value"], f"{context}.raw_value"),
        normalized_value=string_tuple(data["normalized_value"], f"{context}.normalized_value"),
        qualifiers=string_tuple(data["qualifiers"], f"{context}.qualifiers"),
        status=enum_value(DecisionStatus, data["status"], f"{context}.status"),
        source_round=as_string(data["source_round"], f"{context}.source_round"),
        source_question=as_string(data["source_question"], f"{context}.source_question"),
    )


def encode_question(question: Question) -> dict[str, JsonValue]:
    return {
        "question_id": question.question_id,
        "text": question.text,
        "question_type": question.question_type.value,
        "options": [encode_option(item) for item in question.options],
        "recommendation": encode_recommendation(question.recommendation),
        "owner_answer": (
            encode_owner_answer(question.owner_answer) if question.owner_answer is not None else None
        ),
        "answer_status": question.answer_status.value,
        "derived_implications": list(question.derived_implications),
        "trace_refs": list(question.trace_refs),
    }


def decode_question(value: Any, context: str) -> Question:
    data = strict_object(
        value,
        {
            "question_id",
            "text",
            "question_type",
            "options",
            "recommendation",
            "owner_answer",
            "answer_status",
            "derived_implications",
            "trace_refs",
        },
        context,
    )
    answer = (
        None
        if data["owner_answer"] is None
        else decode_owner_answer(data["owner_answer"], f"{context}.owner_answer")
    )
    return Question(
        question_id=as_string(data["question_id"], f"{context}.question_id"),
        text=as_string(data["text"], f"{context}.text"),
        question_type=enum_value(
            QuestionType, data["question_type"], f"{context}.question_type"
        ),
        options=tuple(
            decode_option(item, f"{context}.options[{index}]")
            for index, item in enumerate(as_list(data["options"], f"{context}.options"))
        ),
        recommendation=decode_recommendation(
            data["recommendation"], f"{context}.recommendation"
        ),
        owner_answer=answer,
        answer_status=enum_value(
            DecisionStatus, data["answer_status"], f"{context}.answer_status"
        ),
        derived_implications=string_tuple(
            data["derived_implications"], f"{context}.derived_implications"
        ),
        trace_refs=string_tuple(data["trace_refs"], f"{context}.trace_refs"),
    )


def encode_round(value: DesignRound) -> dict[str, JsonValue]:
    return {
        "round_id": value.round_id,
        "topic": value.topic,
        "purpose": value.purpose,
        "prerequisites": list(value.prerequisites),
        "questions": [encode_question(item) for item in value.questions],
        "owner_answer_set": [
            {"question_id": question_id, "answer": encode_owner_answer(answer)}
            for question_id, answer in value.owner_answer_set.items()
        ],
        "synthesis": list(value.synthesis),
        "derived_rules": list(value.derived_rules),
        "unresolved": list(value.unresolved),
        "conflicts_detected": list(value.conflicts_detected),
        "status": value.status.value,
        "trace_refs": list(value.trace_refs),
    }


def decode_round(value: Any, context: str) -> DesignRound:
    data = strict_object(
        value,
        {
            "round_id",
            "topic",
            "purpose",
            "prerequisites",
            "questions",
            "owner_answer_set",
            "synthesis",
            "derived_rules",
            "unresolved",
            "conflicts_detected",
            "status",
            "trace_refs",
        },
        context,
    )
    answers: dict[str, OwnerAnswer] = {}
    for index, item in enumerate(as_list(data["owner_answer_set"], f"{context}.owner_answer_set")):
        answer_data = strict_object(
            item,
            {"question_id", "answer"},
            f"{context}.owner_answer_set[{index}]",
        )
        question_id = as_string(
            answer_data["question_id"], f"{context}.owner_answer_set[{index}].question_id"
        )
        if question_id in answers:
            raise SchemaError(f"{context} repeats owner answer for {question_id}")
        answers[question_id] = decode_owner_answer(
            answer_data["answer"], f"{context}.owner_answer_set[{index}].answer"
        )
    return DesignRound(
        round_id=as_string(data["round_id"], f"{context}.round_id"),
        topic=as_string(data["topic"], f"{context}.topic"),
        purpose=as_string(data["purpose"], f"{context}.purpose"),
        prerequisites=string_tuple(data["prerequisites"], f"{context}.prerequisites"),
        questions=tuple(
            decode_question(item, f"{context}.questions[{index}]")
            for index, item in enumerate(as_list(data["questions"], f"{context}.questions"))
        ),
        owner_answer_set=answers,
        synthesis=string_tuple(data["synthesis"], f"{context}.synthesis"),
        derived_rules=string_tuple(data["derived_rules"], f"{context}.derived_rules"),
        unresolved=string_tuple(data["unresolved"], f"{context}.unresolved"),
        conflicts_detected=string_tuple(
            data["conflicts_detected"], f"{context}.conflicts_detected"
        ),
        status=enum_value(DecisionStatus, data["status"], f"{context}.status"),
        trace_refs=string_tuple(data["trace_refs"], f"{context}.trace_refs"),
    )


def encode_provenance(value: DecisionProvenance) -> dict[str, JsonValue]:
    return {
        "recommendation_was": list(value.recommendation_was),
        "recommendation_reason": value.recommendation_reason,
        "owner_raw_value": value.owner_raw_value,
        "owner_normalized_value": list(value.owner_normalized_value),
        "owner_qualifiers": list(value.owner_qualifiers),
        "question_text": value.question_text,
        "options": [encode_option(item) for item in value.options],
        "rule_source_value": list(value.rule_source_value),
    }


def decode_provenance(value: Any, context: str) -> DecisionProvenance:
    data = strict_object(
        value,
        {
            "recommendation_was",
            "recommendation_reason",
            "owner_raw_value",
            "owner_normalized_value",
            "owner_qualifiers",
            "question_text",
            "options",
            "rule_source_value",
        },
        context,
    )
    return DecisionProvenance(
        recommendation_was=string_tuple(
            data["recommendation_was"], f"{context}.recommendation_was"
        ),
        recommendation_reason=as_string(
            data["recommendation_reason"], f"{context}.recommendation_reason"
        ),
        owner_raw_value=as_string(data["owner_raw_value"], f"{context}.owner_raw_value"),
        owner_normalized_value=string_tuple(
            data["owner_normalized_value"], f"{context}.owner_normalized_value"
        ),
        owner_qualifiers=string_tuple(
            data["owner_qualifiers"], f"{context}.owner_qualifiers"
        ),
        question_text=as_string(data["question_text"], f"{context}.question_text"),
        options=tuple(
            decode_option(item, f"{context}.options[{index}]")
            for index, item in enumerate(as_list(data["options"], f"{context}.options"))
        ),
        rule_source_value=string_tuple(
            data["rule_source_value"], f"{context}.rule_source_value"
        ),
    )


def encode_decision(value: Decision) -> dict[str, JsonValue]:
    return {
        "decision_id": value.decision_id,
        "canonical_rule": value.canonical_rule,
        "authoritative_value": list(value.authoritative_value),
        "status": value.status.value,
        "scope": value.scope,
        "source_round": value.source_round,
        "source_question": value.source_question,
        "provenance": encode_provenance(value.provenance),
        "dependencies": list(value.dependencies),
        "supersedes": list(value.supersedes),
        "unresolved_consequences": list(value.unresolved_consequences),
        "trace_refs": list(value.trace_refs),
    }


def decode_decision(value: Any, context: str) -> Decision:
    data = strict_object(
        value,
        {
            "decision_id",
            "canonical_rule",
            "authoritative_value",
            "status",
            "scope",
            "source_round",
            "source_question",
            "provenance",
            "dependencies",
            "supersedes",
            "unresolved_consequences",
            "trace_refs",
        },
        context,
    )
    return Decision(
        decision_id=as_string(data["decision_id"], f"{context}.decision_id"),
        canonical_rule=as_string(data["canonical_rule"], f"{context}.canonical_rule"),
        authoritative_value=string_tuple(
            data["authoritative_value"], f"{context}.authoritative_value"
        ),
        status=enum_value(DecisionStatus, data["status"], f"{context}.status"),
        scope=as_string(data["scope"], f"{context}.scope"),
        source_round=as_string(data["source_round"], f"{context}.source_round"),
        source_question=as_string(data["source_question"], f"{context}.source_question"),
        provenance=decode_provenance(data["provenance"], f"{context}.provenance"),
        dependencies=string_tuple(data["dependencies"], f"{context}.dependencies"),
        supersedes=string_tuple(data["supersedes"], f"{context}.supersedes"),
        unresolved_consequences=string_tuple(
            data["unresolved_consequences"], f"{context}.unresolved_consequences"
        ),
        trace_refs=string_tuple(data["trace_refs"], f"{context}.trace_refs"),
    )


def encode_relationship(value: ConflictRecord) -> dict[str, JsonValue]:
    return {
        "earlier_decision": value.earlier_decision,
        "later_decision": value.later_decision,
        "relation": value.relation.value,
        "notes": value.notes,
    }


def decode_relationship(value: Any, context: str) -> ConflictRecord:
    data = strict_object(
        value,
        {"earlier_decision", "later_decision", "relation", "notes"},
        context,
    )
    return ConflictRecord(
        earlier_decision=as_string(
            data["earlier_decision"], f"{context}.earlier_decision"
        ),
        later_decision=as_string(data["later_decision"], f"{context}.later_decision"),
        relation=enum_value(ConflictRelation, data["relation"], f"{context}.relation"),
        notes=as_string(data["notes"], f"{context}.notes"),
    )


def encode_concept(value: CoreConcept) -> dict[str, JsonValue]:
    return {
        "concept_id": value.concept_id,
        "canonical_name": value.canonical_name,
        "version": value.version,
        "status": value.status.value,
        "maturity": value.maturity.value,
        "scope": value.scope,
        "definition": value.definition,
        "owns": list(value.owns),
        "does_not_own": list(value.does_not_own),
        "boundaries": list(value.boundaries),
        "dependencies": list(value.dependencies),
        "relations": list(value.relations),
        "source_decisions": list(value.source_decisions),
        "unresolved": list(value.unresolved),
        "supersedes": list(value.supersedes),
        "provenance": to_plain(value.provenance),
        "trace_refs": list(value.trace_refs),
    }


def decode_concept(value: Any, context: str) -> CoreConcept:
    data = strict_object(
        value,
        {
            "concept_id",
            "canonical_name",
            "version",
            "status",
            "maturity",
            "scope",
            "definition",
            "owns",
            "does_not_own",
            "boundaries",
            "dependencies",
            "relations",
            "source_decisions",
            "unresolved",
            "supersedes",
            "provenance",
            "trace_refs",
        },
        context,
    )
    if type(data["provenance"]) is not dict:
        raise SchemaError(f"{context}.provenance must be an object")
    return CoreConcept(
        concept_id=as_string(data["concept_id"], f"{context}.concept_id"),
        canonical_name=as_string(data["canonical_name"], f"{context}.canonical_name"),
        version=as_string(data["version"], f"{context}.version"),
        status=enum_value(ConceptStatus, data["status"], f"{context}.status"),
        maturity=enum_value(ConceptMaturity, data["maturity"], f"{context}.maturity"),
        scope=as_string(data["scope"], f"{context}.scope"),
        definition=as_string(data["definition"], f"{context}.definition"),
        owns=string_tuple(data["owns"], f"{context}.owns"),
        does_not_own=string_tuple(data["does_not_own"], f"{context}.does_not_own"),
        boundaries=string_tuple(data["boundaries"], f"{context}.boundaries"),
        dependencies=string_tuple(data["dependencies"], f"{context}.dependencies"),
        relations=string_tuple(data["relations"], f"{context}.relations"),
        source_decisions=string_tuple(
            data["source_decisions"], f"{context}.source_decisions"
        ),
        unresolved=string_tuple(data["unresolved"], f"{context}.unresolved"),
        supersedes=string_tuple(data["supersedes"], f"{context}.supersedes"),
        provenance=data["provenance"],
        trace_refs=string_tuple(data["trace_refs"], f"{context}.trace_refs"),
    )


def encode_trace(value: TraceRecord) -> dict[str, JsonValue]:
    return {
        "trace_id": value.trace_id,
        "action": value.action.value,
        "entity_type": value.entity_type,
        "entity_id": value.entity_id,
        "details": to_plain(value.details),
    }


def decode_trace(value: Any, context: str) -> TraceRecord:
    data = strict_object(
        value,
        {"trace_id", "action", "entity_type", "entity_id", "details"},
        context,
    )
    if type(data["details"]) is not dict:
        raise SchemaError(f"{context}.details must be an object")
    return TraceRecord(
        trace_id=as_string(data["trace_id"], f"{context}.trace_id"),
        action=enum_value(TraceAction, data["action"], f"{context}.action"),
        entity_type=as_string(data["entity_type"], f"{context}.entity_type"),
        entity_id=as_string(data["entity_id"], f"{context}.entity_id"),
        details=freeze_semantic_value(data["details"]),
    )
