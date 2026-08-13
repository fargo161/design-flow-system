"""Small command-oriented runner over an explicitly selected project."""

from __future__ import annotations

from pathlib import Path

from .model import DesignFlowMode
from .project import PersistentProject
from .unresolved import compile_unresolved_register


HELP = """Commands:
STATE                  current committed rules and session brief
LEDGER                 complete decision ledger
UNRESOLVED             committed unresolved register
CONCEPTS               current and affected concepts
TRACE                  chronological TRACE
ROUND                  current non-authoritative draft
IMPORT DRAFT <path>    originate a strict JSON draft
ANSWER <question> <raw owner answer>
EDIT <question> <raw owner answer>
PREVIEW                 non-authoritative draft synthesis
LOCK                    explicitly commit the complete draft
ABANDON                 discard the draft only
SAVE                    storage checkpoint (not semantic history)
COMPILE                 regenerate living application and context handoff
HELP
END SESSION
"""


class CommandRunner:
    """Execute clear inspection/working commands; project selection stays external."""

    def __init__(self, project: PersistentProject) -> None:
        self.project = project

    def execute(self, command_line: str) -> str:
        command, _, argument = command_line.strip().partition(" ")
        command = command.upper()
        if command == "HELP":
            return HELP
        if command == "STATE":
            brief = self.project.session_brief()
            rules = "\n".join(f"- {item}" for item in brief.current_rules) or "- none"
            return (
                f"Project: {brief.name} (`{brief.project_id}`)\n"
                f"Mode: {brief.mode}\nCurrent rules:\n{rules}\n"
                f"Recommended next round: {brief.recommended_next_round}\n"
                f"Why: {brief.recommendation_reason}"
            )
        if command == "LEDGER":
            return "\n".join(
                f"{item.decision_id} [{item.status.value}] {item.canonical_rule}"
                for item in self.project.workspace.ledger.decisions
            ) or "No committed decisions."
        if command == "UNRESOLVED":
            unresolved = compile_unresolved_register(self.project.workspace)
            return "\n".join(unresolved) or "No unresolved items."
        if command == "CONCEPTS":
            return "\n".join(
                f"{item.concept_id} [{item.status.value}] {item.definition}"
                for item in (
                    *self.project.workspace.concepts.concepts,
                    *self.project.workspace.concepts.affected,
                )
            ) or "No core concepts."
        if command == "TRACE":
            return "\n".join(
                f"{item.trace_id} {item.action.value} {item.entity_type} {item.entity_id}"
                for item in self.project.workspace.trace.records
            )
        if command == "ROUND":
            draft = self.project.draft
            if draft is None:
                return "No active draft round."
            answers = ", ".join(sorted(draft.answers)) or "none"
            return (
                "DRAFT — NON-AUTHORITATIVE\n"
                f"{draft.round_id}: {draft.topic}\nAnswered: {answers}\n"
                f"Complete: {'yes' if draft.complete else 'no'}"
            )
        if command == "IMPORT" and argument.upper().startswith("DRAFT "):
            path = argument[6:].strip()
            if not path:
                raise ValueError("Usage: IMPORT DRAFT <path>")
            draft = self.project.import_draft(path)
            return (
                f"Imported draft {draft.draft_id} for round {draft.round_id}; "
                "still non-authoritative."
            )
        if command in {"ANSWER", "EDIT"}:
            question_id, separator, raw_answer = argument.partition(" ")
            if not separator or not raw_answer.strip():
                raise ValueError(f"Usage: {command} <question_id> <raw owner answer>")
            self.project.answer_draft(question_id, raw_answer)
            return f"Draft answer saved for {question_id}; still non-authoritative."
        if command == "PREVIEW":
            preview = self.project.preview_draft()
            lines = [preview.label]
            lines.extend(f"Rule: {item}" for item in preview.derived_rules)
            lines.extend(
                f"Potential supersession: {item}" for item in preview.potential_supersessions
            )
            lines.extend(f"Affected concept: {item}" for item in preview.affected_concepts)
            lines.extend(f"Unresolved: {item}" for item in preview.unresolved)
            lines.extend(f"BLOCKER: {item}" for item in preview.errors)
            return "\n".join(lines)
        if command == "LOCK":
            committed = self.project.lock_draft()
            recommendation = self.project.session_brief()
            return (
                f"Committed round {committed.round_id}.\n"
                f"Recommended next round: {recommendation.recommended_next_round}\n"
                f"Why: {recommendation.recommendation_reason}"
                f"{self.project.storage_warning_suffix()}"
            )
        if command == "ABANDON":
            self.project.abandon_draft()
            return "Draft abandoned; committed authority was unchanged."
        if command == "SAVE":
            manifest = self.project.save()
            return (
                f"Saved generation {manifest.save_generation}."
                f"{self.project.storage_warning_suffix()}"
            )
        if command == "COMPILE":
            paths = self.project.compile_artifacts()
            return (
                "Generated: " + ", ".join(paths) + self.project.storage_warning_suffix()
            )
        if command == "END" and argument.strip().upper() == "SESSION":
            session = self.project.end_session()
            return f"Ended session {session.session_id}."
        raise ValueError(f"Unknown command: {command or '<empty>'}. Use HELP.")


def run_console(project: PersistentProject) -> None:
    """Run after the caller explicitly chose NEW PROJECT or RESUME PROJECT."""

    runner = CommandRunner(project)
    print(runner.execute("STATE"))
    while project.active_session is not None:
        try:
            print(runner.execute(input("design-flow> ")))
        except (EOFError, KeyboardInterrupt):
            print("\nSession remains open; use END SESSION for an explicit persisted close.")
            break
        except (KeyError, TypeError, ValueError) as error:
            print(f"ERROR: {error}")


def main() -> None:
    """Require an explicit NEW PROJECT or RESUME PROJECT choice."""

    print("NEW PROJECT\nRESUME PROJECT")
    choice = input("design-flow selection> ").strip().upper()
    if choice == "NEW PROJECT":
        path = Path(input("Project directory> ").strip())
        project = PersistentProject.create(
            path,
            project_id=input("Stable project ID> ").strip(),
            name=input("Project name> ").strip(),
            description=input("Project description> ").strip(),
            mode=DesignFlowMode(input("Mode [DISCOVERY/REFINEMENT/REPAIR]> ").strip().upper()),
            authority=input("Owner authority statement> ").strip(),
        )
    elif choice == "RESUME PROJECT":
        project = PersistentProject.resume(Path(input("Project directory> ").strip()))
        brief = project.session_brief()
        print(
            f"Session Brief\nProject: {brief.name} (`{brief.project_id}`)\n"
            f"Mode: {brief.mode}\nLast completed round: "
            f"{brief.last_completed_round or 'none'}\n"
            f"Recommended next round: {brief.recommended_next_round}\n"
            f"Why: {brief.recommendation_reason}"
        )
    else:
        raise ValueError("Choose exactly NEW PROJECT or RESUME PROJECT")
    if project.active_session is None:
        project.start_session()
    run_console(project)


if __name__ == "__main__":
    main()
