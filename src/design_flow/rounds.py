"""Round registration and deterministic owner-answer intake."""

from __future__ import annotations

import re

from .model import (
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
    def __init__(self, project: Project, trace: TraceLog) -> None:
        self.project = project
        self.trace = trace
        self._rounds: dict[str, DesignRound] = {}

    @property
    def rounds(self) -> tuple[DesignRound, ...]:
        return tuple(self._rounds.values())

    def register_round(self, design_round: DesignRound) -> DesignRound:
        if design_round.round_id in self._rounds:
            raise ValueError(f"Round already exists: {design_round.round_id}")
        self._rounds[design_round.round_id] = design_round
        trace_id = self.trace.record(
            TraceAction.REGISTER_ROUND,
            "round",
            design_round.round_id,
            topic=design_round.topic,
            mode=self.project.current_mode.value,
        )
        design_round.trace_refs.append(trace_id)
        return design_round

    def get(self, round_id: str) -> DesignRound:
        try:
            return self._rounds[round_id]
        except KeyError as error:
            raise KeyError(f"Unknown round: {round_id}") from error

    def add_question(self, round_id: str, question: Question) -> Question:
        design_round = self.get(round_id)
        if any(item.question_id == question.question_id for item in design_round.questions):
            raise ValueError(f"Question already exists: {question.question_id}")
        design_round.questions.append(question)
        question.trace_refs.append(
            self.trace.record(
                TraceAction.REGISTER_QUESTION,
                "question",
                question.question_id,
                round_id=round_id,
                question_type=question.question_type.value,
            )
        )
        question.trace_refs.append(
            self.trace.record(
                TraceAction.RECOMMEND,
                "question",
                question.question_id,
                proposed_answer=list(question.recommendation.proposed_answer),
                reason=question.recommendation.reason,
            )
        )
        return question

    def record_owner_answer(self, round_id: str, question_id: str, raw_value: str) -> OwnerAnswer:
        design_round = self.get(round_id)
        question = design_round.question(question_id)
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
        question.owner_answer = answer
        question.answer_status = answer.status
        design_round.owner_answer_set[question_id] = answer
        question.trace_refs.append(
            self.trace.record(
                TraceAction.OWNER_SELECT,
                "question",
                question_id,
                raw_value=answer.raw_value,
                normalized_value=list(answer.normalized_value),
                qualifiers=list(answer.qualifiers),
                status=answer.status.value,
            )
        )

        if answer.status is DecisionStatus.UNRESOLVED:
            follow_up = self._follow_up_for(answer)
            if follow_up not in design_round.unresolved:
                design_round.unresolved.append(follow_up)
            question.derived_implications.append(follow_up)
            question.trace_refs.append(
                self.trace.record(
                    TraceAction.MARK_UNRESOLVED,
                    "question",
                    question_id,
                    follow_up=follow_up,
                )
            )

        self._refresh_round_status(design_round)
        return answer

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
    def _refresh_round_status(design_round: DesignRound) -> None:
        if not design_round.questions or len(design_round.owner_answer_set) < len(design_round.questions):
            design_round.status = DecisionStatus.OPEN
        elif any(answer.status is DecisionStatus.UNRESOLVED for answer in design_round.owner_answer_set.values()):
            design_round.status = DecisionStatus.UNRESOLVED
        else:
            design_round.status = DecisionStatus.OWNER_SELECTED
