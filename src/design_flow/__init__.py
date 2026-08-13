"""Public API; DesignFlowWorkspace is the canonical full-integrity boundary."""

from .concepts import CoreConceptRegistry
from .decisions import CurrentStateCompiler, DecisionLedger, DecisionSynthesizer
from .documents import LivingApplicationDocumentRenderer
from .intake import DesignFlowWorkspace
from .model import (
    ApplicationBinding,
    ConceptMaturity,
    ConceptStatus,
    ConflictRelation,
    CoreConcept,
    CurrentDesignState,
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
)
from .rounds import RoundManager, parse_owner_answer
from .trace import TraceLog
from .handoff import RoundRecommendation, compile_context_handoff, recommend_next_round
from .llm import LLMAdapter, LLMUnavailableError, request_draft
from .persistence import ProjectStore, ProjectValidationError, SourceReference
from .project import PersistentProject, SessionBrief
from .runner import CommandRunner
from .session import (
    DraftConceptAction,
    DraftConceptPlan,
    DraftDecisionPlan,
    DraftPreview,
    DraftQuestion,
    DraftRound,
    SessionRecord,
)
from .unresolved import compile_unresolved_register

__all__ = [
    "ApplicationBinding",
    "ConceptMaturity",
    "ConceptStatus",
    "ConflictRelation",
    "CoreConcept",
    "CoreConceptRegistry",
    "CurrentDesignState",
    "CurrentStateCompiler",
    "Decision",
    "DecisionLedger",
    "DecisionProvenance",
    "DecisionStatus",
    "DecisionSynthesizer",
    "DesignFlowMode",
    "DesignFlowWorkspace",
    "DesignRound",
    "LivingApplicationDocumentRenderer",
    "OwnerAnswer",
    "Project",
    "Question",
    "QuestionOption",
    "QuestionType",
    "Recommendation",
    "RoundManager",
    "TraceAction",
    "TraceLog",
    "TraceRecord",
    "parse_owner_answer",
    "CommandRunner",
    "DraftConceptAction",
    "DraftConceptPlan",
    "DraftDecisionPlan",
    "DraftPreview",
    "DraftQuestion",
    "DraftRound",
    "LLMAdapter",
    "LLMUnavailableError",
    "PersistentProject",
    "ProjectStore",
    "ProjectValidationError",
    "RoundRecommendation",
    "SessionBrief",
    "SessionRecord",
    "SourceReference",
    "compile_context_handoff",
    "recommend_next_round",
    "request_draft",
    "compile_unresolved_register",
]

__version__ = "0.2.0"
