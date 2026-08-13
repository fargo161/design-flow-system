"""Round registration and deterministic owner-answer intake."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace

from .model import (
    Decision,
    DecisionStatus,
    DesignRound,
    OwnerAnswer,
    Project,
    Question,
    TraceAction,
)
from .trace import TraceLog


def parse_owner_answer(
    raw_value: str,
    *,
    allowed_values: tuple[str, ...],
    source_round: str,
    source_question: str,
    aliases: dict[str, str] | None = None,
) -> OwnerAnswer:
    """Preserve bounded selections and any qualification without guessing.

    This is intentionally not a free-text interpretation engine. It recognizes
    declared option keys and preserves every remaining word as qualification.
    """

    raw = raw_value.strip()
    if not raw:
        raise ValueError("Owner answers cannot be empty")

    normalized_allowed = tuple(value.upper() for value in allowed_values)
    normalized_aliases = {key.upper(): value.upper() for key, value in (aliases or {}).items()}
    recognized_tokens = (*normalized_allowed, *normalized_aliases)
    alternatives = "|".join(
        re.escape(value) for value in sorted(recognized_tokens, key=len, reverse=True)
    )
    pattern = re.compile(rf"(?<![A-Z0-9])(?:{alternatives})(?![A-Z0-9])", re.IGNORECASE)

    selections: list[str] = []
    for match in pattern.finditer(raw):
        token = match.group(0).upper()
        value = normalized_aliases.get(token, token)
        if value not in selections:
            selections.append(value)

    qualifier_text = pattern.sub(" ", raw)
    qualifier_text = re.sub(r"\s*(?:\+|/|&|,)\s*", " ", qualifier_text)
    qualifier_text = re.sub(r"\s+", " ", qualifier_text).strip(" .;:-")
    qualifiers = (qualifier_text,) if qualifier_text else ()

    status = (
        DecisionStatus.OWNER_SELECTED
        if len(selections) == 1 and not qualifiers
        else DecisionStatus.UNRESOLVED
    )
    return OwnerAnswer(
        raw_value=raw,
        normalized_value=tuple(selections),
        qualifiers=qualifiers,
        status=status,
        source_round=source_round,
        source_question=source_question,
    )


class RoundManager:
    def __init__(
        self,
        project: Project,
        trace: TraceLog,
        registered_decisions: Callable[[], tuple[Decision, ...]],
    ) -> None:
        self.project = project
        self.trace = trace
        self._registered_decisions = registered_decisions
        self._rounds: dict[str, DesignRound] = {}

    @property
    def rounds(self) -> tuple[DesignRound, ...]:
        return tuple(self._rounds.values())

    def restore(self, rounds: tuple[DesignRound, ...]) -> None:
        """Restore authoritative round history without emitting TRACE."""

        if len({item.round_id for item in rounds}) != len(rounds):
            raise ValueError("Round identifiers must be unique")
        self._rounds = {item.round_id: item for item in rounds}

    def register_round(self, design_round: DesignRound) -> DesignRound:
        if design_round.round_id in self._rounds:
            raise ValueError(f"Round already exists: {design_round.round_id}")
        trace_id = self.trace.record(
            TraceAction.REGISTER_ROUND,
            "round",
            design_round.round_id,
            topic=design_round.topic,
            purpose=design_round.purpose,
            prerequisites=list(design_round.prerequisites),
            mode=self.project.current_mode.value,
        )
        registered = replace(
            design_round, trace_refs=(*design_round.trace_refs, trace_id)
        )
        self._rounds[design_round.round_id] = registered
        return registered

    def get(self, round_id: str) -> DesignRound:
        try:
            return self._rounds[round_id]
        except KeyError as error:
            raise KeyError(f"Unknown round: {round_id}") from error

    def add_question(self, round_id: str, question: Question) -> Question:
        design_round = self.get(round_id)
        if any(item.question_id == question.question_id for item in design_round.questions):
            raise ValueError(f"Question already exists: {question.question_id}")
        trace_refs = (
            self.trace.record(
                TraceAction.REGISTER_QUESTION,
                "question",
                question.question_id,
                round_id=round_id,
                question_type=question.question_type.value,
                question_text=question.text,
                options=[(option.key, option.label) for option in question.options],
            ),
            self.trace.record(
                TraceAction.RECOMMEND,
                "question",
                question.question_id,
                proposed_answer=list(question.recommendation.proposed_answer),
                reason=question.recommendation.reason,
                status=question.recommendation.status.value,
            ),
        )
        registered = replace(question, trace_refs=trace_refs)
        self._rounds[round_id] = replace(
            design_round, questions=(*design_round.questions, registered)
        )
        return registered

    def record_owner_answer(self, round_id: str, question_id: str, raw_value: str) -> OwnerAnswer:
        design_round = self.get(round_id)
        question = design_round.question(question_id)
        if question.owner_answer is not None:
            raise ValueError(
                "Owner answer history is immutable; edit a draft or create a superseding decision"
            )
        answer = parse_owner_answer(
            raw_value,
            allowed_values=question.option_keys,
            source_round=round_id,
            source_question=question_id,
            aliases=(
                {option.label: option.key for option in question.options}
                if question.question_type.value == "YES_NO"
                else None
            ),
        )
        trace_refs = (
            *question.trace_refs,
            self.trace.record(
                TraceAction.OWNER_SELECT,
                "question",
                question_id,
                raw_value=answer.raw_value,
                normalized_value=list(answer.normalized_value),
                qualifiers=list(answer.qualifiers),
                status=answer.status.value,
            ),
        )
        implications = question.derived_implications
        unresolved = design_round.unresolved

        if answer.status is DecisionStatus.UNRESOLVED:
            follow_up = self._follow_up_for(answer)
            if follow_up not in unresolved:
                unresolved = (*unresolved, follow_up)
            implications = (*implications, follow_up)
            trace_refs = (
                *trace_refs,
                self.trace.record(
                    TraceAction.MARK_UNRESOLVED,
                    "question",
                    question_id,
                    follow_up=follow_up,
                ),
            )
        updated_question = replace(
            question,
            owner_answer=answer,
            answer_status=answer.status,
            derived_implications=implications,
            trace_refs=trace_refs,
        )
        answers = dict(design_round.owner_answer_set)
        answers[question_id] = answer
        questions = tuple(
            updated_question if item.question_id == question_id else item
            for item in design_round.questions
        )
        updated_round = replace(
            design_round,
            questions=questions,
            owner_answer_set=answers,
            unresolved=unresolved,
        )
        updated_round = replace(updated_round, status=self._round_status(updated_round))
        self._rounds[round_id] = updated_round
        return answer

    def _synchronize_decision_history(self, round_id: str) -> DesignRound:
        """Derive committed synthesis solely from registered ledger decisions."""

        design_round = self.get(round_id)
        sourced = tuple(
            decision
            for decision in self._registered_decisions()
            if decision.source_round == round_id
        )
        for decision in sourced:
            self.trace.validate_registered_decision(decision)
        canonical_rules = tuple(decision.canonical_rule for decision in sourced)
        updated = replace(
            design_round,
            synthesis=canonical_rules,
            derived_rules=canonical_rules,
        )
        self._rounds[round_id] = updated
        return updated

    def record_owner_answers(self, round_id: str, compact_answers: str) -> dict[str, OwnerAnswer]:
        """Record strings such as ``1B, 2A, 3 Yes`` by question order."""

        design_round = self.get(round_id)
        recorded: dict[str, OwnerAnswer] = {}
        parts = [part.strip() for part in compact_answers.split(",") if part.strip()]
        for part in parts:
            match = re.fullmatch(r"(\d+)\s*(.+)", part)
            if not match:
                raise ValueError(f"Invalid compact answer segment: {part!r}")
            index = int(match.group(1)) - 1
            if index < 0 or index >= len(design_round.questions):
                raise ValueError(f"Question number is out of range: {index + 1}")
            question_id = design_round.questions[index].question_id
            recorded[question_id] = self.record_owner_answer(round_id, question_id, match.group(2))
        return recorded

    @staticmethod
    def _follow_up_for(answer: OwnerAnswer) -> str:
        if len(answer.normalized_value) > 1:
            choices = " and ".join(answer.normalized_value)
            return f"Determine the contextual discriminator between {choices}."
        if answer.normalized_value and answer.qualifier:
            return f"Resolve the boundary for {answer.normalized_value[0]}: {answer.qualifier}."
        return f"Clarify the owner answer for {answer.source_question}."

    @staticmethod
    def _round_status(design_round: DesignRound) -> DecisionStatus:
        if not design_round.questions or len(design_round.owner_answer_set) < len(design_round.questions):
            return DecisionStatus.OPEN
        elif any(answer.status is DecisionStatus.UNRESOLVED for answer in design_round.owner_answer_set.values()):
            return DecisionStatus.UNRESOLVED
        return DecisionStatus.OWNER_SELECTED
