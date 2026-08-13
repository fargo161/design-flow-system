"""Persistent non-authoritative drafts and bounded session metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from .codec import (
    JsonValue,
    SchemaError,
    as_list,
    as_string,
    decode_option,
    decode_recommendation,
    encode_option,
    encode_recommendation,
    enum_value,
    strict_object,
    string_tuple,
)
from .model import ConceptMaturity, QuestionOption, QuestionType, Recommendation


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class DraftConceptAction(StrEnum):
    REGISTER = "REGISTER"
    REVISE = "REVISE"


@dataclass(slots=True, frozen=True)
class SessionRecord:
    session_id: str
    project_id: str
    started_at: str
    ended_at: str | None = None
    rounds_touched: tuple[str, ...] = ()
    rounds_committed: tuple[str, ...] = ()
    save_generations: tuple[int, ...] = ()
    artifacts_generated: tuple[str, ...] = ()

    def touch_round(self, round_id: str) -> "SessionRecord":
        return replace(
            self,
            rounds_touched=tuple(dict.fromkeys((*self.rounds_touched, round_id))),
        )

    def commit_round(self, round_id: str) -> "SessionRecord":
        return replace(
            self.touch_round(round_id),
            rounds_committed=tuple(dict.fromkeys((*self.rounds_committed, round_id))),
        )

    def record_generation(self, generation: int) -> "SessionRecord":
        return replace(self, save_generations=(*self.save_generations, generation))

    def record_artifacts(self, paths: tuple[str, ...]) -> "SessionRecord":
        return replace(
            self,
            artifacts_generated=tuple(dict.fromkeys((*self.artifacts_generated, *paths))),
        )

    def end(self, ended_at: str | None = None) -> "SessionRecord":
        return replace(self, ended_at=ended_at or utc_now())


@dataclass(slots=True, frozen=True)
class DraftQuestion:
    question_id: str
    text: str
    question_type: QuestionType
    options: tuple[QuestionOption, ...]
    recommendation: Recommendation


@dataclass(slots=True, frozen=True)
class DraftConceptPlan:
    action: DraftConceptAction
    concept_id: str
    canonical_name: str
    definition: str
    version: str = "0.2.0"
    maturity: ConceptMaturity = ConceptMaturity.DEFINED
    owns: tuple[str, ...] = ()
    does_not_own: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class DraftDecisionPlan:
    question_id: str
    decision_id: str
    scope: str
    rule_mapping: tuple[tuple[tuple[str, ...], str], ...]
    dependencies: tuple[str, ...] = ()
    unresolved_consequences: tuple[str, ...] = ()
    supersedes_decision: str | None = None
    supersession_notes: str = ""
    concept: DraftConceptPlan | None = None

    @classmethod
    def create(
        cls,
        *,
        question_id: str,
        decision_id: str,
        scope: str,
        rule_mapping: Mapping[str | tuple[str, ...], str],
        dependencies: tuple[str, ...] = (),
        unresolved_consequences: tuple[str, ...] = (),
        supersedes_decision: str | None = None,
        supersession_notes: str = "",
        concept: DraftConceptPlan | None = None,
    ) -> "DraftDecisionPlan":
        normalized = tuple(
            (
                (key,) if type(key) is str else tuple(key),
                value,
            )
            for key, value in rule_mapping.items()
        )
        return cls(
            question_id=question_id,
            decision_id=decision_id,
            scope=scope,
            rule_mapping=normalized,
            dependencies=dependencies,
            unresolved_consequences=unresolved_consequences,
            supersedes_decision=supersedes_decision,
            supersession_notes=supersession_notes,
            concept=concept,
        )

    def rules(self) -> dict[str | tuple[str, ...], str]:
        return {
            key[0] if len(key) == 1 else key: value
            for key, value in self.rule_mapping
        }


@dataclass(slots=True, frozen=True)
class DraftRound:
    draft_id: str
    round_id: str
    topic: str
    purpose: str
    questions: tuple[DraftQuestion, ...]
    decisions: tuple[DraftDecisionPlan, ...]
    prerequisites: tuple[str, ...] = ()
    answers: Mapping[str, str] = MappingProxyType({})
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "questions", tuple(self.questions))
        object.__setattr__(self, "decisions", tuple(self.decisions))
        object.__setattr__(self, "prerequisites", tuple(self.prerequisites))
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))
        if len({item.question_id for item in self.questions}) != len(self.questions):
            raise ValueError("Draft question identifiers must be unique")
        question_ids = {item.question_id for item in self.questions}
        if set(self.answers) - question_ids:
            raise ValueError("Draft answers must target declared questions")
        if any(item.question_id not in question_ids for item in self.decisions):
            raise ValueError("Draft decisions must target declared questions")

    @classmethod
    def create(
        cls,
        *,
        draft_id: str,
        round_id: str,
        topic: str,
        purpose: str,
        questions: tuple[DraftQuestion, ...],
        decisions: tuple[DraftDecisionPlan, ...],
        prerequisites: tuple[str, ...] = (),
        created_at: str | None = None,
    ) -> "DraftRound":
        timestamp = created_at or utc_now()
        return cls(
            draft_id=draft_id,
            round_id=round_id,
            topic=topic,
            purpose=purpose,
            questions=questions,
            decisions=decisions,
            prerequisites=prerequisites,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def answer(
        self,
        question_id: str,
        raw_value: str,
        *,
        updated_at: str | None = None,
    ) -> "DraftRound":
        if question_id not in {item.question_id for item in self.questions}:
            raise KeyError(f"Unknown draft question: {question_id}")
        answers = dict(self.answers)
        answers[question_id] = raw_value
        return replace(self, answers=answers, updated_at=updated_at or utc_now())

    @property
    def complete(self) -> bool:
        return all(item.question_id in self.answers for item in self.questions)


@dataclass(slots=True, frozen=True)
class DraftPreview:
    label: str
    derived_rules: tuple[str, ...]
    potential_supersessions: tuple[str, ...]
    affected_concepts: tuple[str, ...]
    unresolved: tuple[str, ...]
    errors: tuple[str, ...] = ()


def encode_session(value: SessionRecord) -> dict[str, JsonValue]:
    return {
        "session_id": value.session_id,
        "project_id": value.project_id,
        "started_at": value.started_at,
        "ended_at": value.ended_at,
        "rounds_touched": list(value.rounds_touched),
        "rounds_committed": list(value.rounds_committed),
        "save_generations": list(value.save_generations),
        "artifacts_generated": list(value.artifacts_generated),
    }


def decode_session(value: Any, context: str) -> SessionRecord:
    data = strict_object(
        value,
        {
            "session_id",
            "project_id",
            "started_at",
            "ended_at",
            "rounds_touched",
            "rounds_committed",
            "save_generations",
            "artifacts_generated",
        },
        context,
    )
    generations = as_list(data["save_generations"], f"{context}.save_generations")
    if any(type(item) is not int for item in generations):
        raise SchemaError(f"{context}.save_generations must contain integers")
    ended = data["ended_at"]
    if ended is not None and type(ended) is not str:
        raise SchemaError(f"{context}.ended_at must be a string or null")
    return SessionRecord(
        session_id=as_string(data["session_id"], f"{context}.session_id"),
        project_id=as_string(data["project_id"], f"{context}.project_id"),
        started_at=as_string(data["started_at"], f"{context}.started_at"),
        ended_at=ended,
        rounds_touched=string_tuple(data["rounds_touched"], f"{context}.rounds_touched"),
        rounds_committed=string_tuple(
            data["rounds_committed"], f"{context}.rounds_committed"
        ),
        save_generations=tuple(generations),
        artifacts_generated=string_tuple(
            data["artifacts_generated"], f"{context}.artifacts_generated"
        ),
    )


def encode_draft_question(value: DraftQuestion) -> dict[str, JsonValue]:
    return {
        "question_id": value.question_id,
        "text": value.text,
        "question_type": value.question_type.value,
        "options": [encode_option(item) for item in value.options],
        "recommendation": encode_recommendation(value.recommendation),
    }


def decode_draft_question(value: Any, context: str) -> DraftQuestion:
    data = strict_object(
        value,
        {"question_id", "text", "question_type", "options", "recommendation"},
        context,
    )
    return DraftQuestion(
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
    )


def encode_concept_plan(value: DraftConceptPlan) -> dict[str, JsonValue]:
    return {
        "action": value.action.value,
        "concept_id": value.concept_id,
        "canonical_name": value.canonical_name,
        "definition": value.definition,
        "version": value.version,
        "maturity": value.maturity.value,
        "owns": list(value.owns),
        "does_not_own": list(value.does_not_own),
        "boundaries": list(value.boundaries),
        "dependencies": list(value.dependencies),
        "relations": list(value.relations),
        "unresolved": list(value.unresolved),
    }


def decode_concept_plan(value: Any, context: str) -> DraftConceptPlan:
    fields = {
        "action",
        "concept_id",
        "canonical_name",
        "definition",
        "version",
        "maturity",
        "owns",
        "does_not_own",
        "boundaries",
        "dependencies",
        "relations",
        "unresolved",
    }
    data = strict_object(value, fields, context)
    return DraftConceptPlan(
        action=enum_value(DraftConceptAction, data["action"], f"{context}.action"),
        concept_id=as_string(data["concept_id"], f"{context}.concept_id"),
        canonical_name=as_string(data["canonical_name"], f"{context}.canonical_name"),
        definition=as_string(data["definition"], f"{context}.definition"),
        version=as_string(data["version"], f"{context}.version"),
        maturity=enum_value(ConceptMaturity, data["maturity"], f"{context}.maturity"),
        owns=string_tuple(data["owns"], f"{context}.owns"),
        does_not_own=string_tuple(data["does_not_own"], f"{context}.does_not_own"),
        boundaries=string_tuple(data["boundaries"], f"{context}.boundaries"),
        dependencies=string_tuple(data["dependencies"], f"{context}.dependencies"),
        relations=string_tuple(data["relations"], f"{context}.relations"),
        unresolved=string_tuple(data["unresolved"], f"{context}.unresolved"),
    )


def encode_decision_plan(value: DraftDecisionPlan) -> dict[str, JsonValue]:
    return {
        "question_id": value.question_id,
        "decision_id": value.decision_id,
        "scope": value.scope,
        "rule_mapping": [
            {"key": list(key), "rule": rule} for key, rule in value.rule_mapping
        ],
        "dependencies": list(value.dependencies),
        "unresolved_consequences": list(value.unresolved_consequences),
        "supersedes_decision": value.supersedes_decision,
        "supersession_notes": value.supersession_notes,
        "concept": encode_concept_plan(value.concept) if value.concept is not None else None,
    }


def decode_decision_plan(value: Any, context: str) -> DraftDecisionPlan:
    fields = {
        "question_id",
        "decision_id",
        "scope",
        "rule_mapping",
        "dependencies",
        "unresolved_consequences",
        "supersedes_decision",
        "supersession_notes",
        "concept",
    }
    data = strict_object(value, fields, context)
    mappings: list[tuple[tuple[str, ...], str]] = []
    for index, item in enumerate(as_list(data["rule_mapping"], f"{context}.rule_mapping")):
        entry = strict_object(item, {"key", "rule"}, f"{context}.rule_mapping[{index}]")
        mappings.append(
            (
                string_tuple(entry["key"], f"{context}.rule_mapping[{index}].key"),
                as_string(entry["rule"], f"{context}.rule_mapping[{index}].rule"),
            )
        )
    supersedes = data["supersedes_decision"]
    if supersedes is not None and type(supersedes) is not str:
        raise SchemaError(f"{context}.supersedes_decision must be a string or null")
    return DraftDecisionPlan(
        question_id=as_string(data["question_id"], f"{context}.question_id"),
        decision_id=as_string(data["decision_id"], f"{context}.decision_id"),
        scope=as_string(data["scope"], f"{context}.scope"),
        rule_mapping=tuple(mappings),
        dependencies=string_tuple(data["dependencies"], f"{context}.dependencies"),
        unresolved_consequences=string_tuple(
            data["unresolved_consequences"], f"{context}.unresolved_consequences"
        ),
        supersedes_decision=supersedes,
        supersession_notes=as_string(
            data["supersession_notes"], f"{context}.supersession_notes"
        ),
        concept=(
            None
            if data["concept"] is None
            else decode_concept_plan(data["concept"], f"{context}.concept")
        ),
    )


def encode_draft(value: DraftRound) -> dict[str, JsonValue]:
    return {
        "draft_id": value.draft_id,
        "round_id": value.round_id,
        "topic": value.topic,
        "purpose": value.purpose,
        "questions": [encode_draft_question(item) for item in value.questions],
        "decisions": [encode_decision_plan(item) for item in value.decisions],
        "prerequisites": list(value.prerequisites),
        "answers": dict(value.answers),
        "created_at": value.created_at,
        "updated_at": value.updated_at,
    }


def decode_draft(value: Any, context: str) -> DraftRound:
    fields = {
        "draft_id",
        "round_id",
        "topic",
        "purpose",
        "questions",
        "decisions",
        "prerequisites",
        "answers",
        "created_at",
        "updated_at",
    }
    data = strict_object(value, fields, context)
    if type(data["answers"]) is not dict or any(
        type(key) is not str or type(item) is not str for key, item in data["answers"].items()
    ):
        raise SchemaError(f"{context}.answers must be a string-to-string object")
    return DraftRound(
        draft_id=as_string(data["draft_id"], f"{context}.draft_id"),
        round_id=as_string(data["round_id"], f"{context}.round_id"),
        topic=as_string(data["topic"], f"{context}.topic"),
        purpose=as_string(data["purpose"], f"{context}.purpose"),
        questions=tuple(
            decode_draft_question(item, f"{context}.questions[{index}]")
            for index, item in enumerate(as_list(data["questions"], f"{context}.questions"))
        ),
        decisions=tuple(
            decode_decision_plan(item, f"{context}.decisions[{index}]")
            for index, item in enumerate(as_list(data["decisions"], f"{context}.decisions"))
        ),
        prerequisites=string_tuple(data["prerequisites"], f"{context}.prerequisites"),
        answers=data["answers"],
        created_at=as_string(data["created_at"], f"{context}.created_at"),
        updated_at=as_string(data["updated_at"], f"{context}.updated_at"),
    )
