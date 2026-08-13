"""Versioned deterministic project storage and semantic activation for v0.2."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .codec import (
    JsonValue,
    SchemaError,
    as_int,
    as_list,
    as_string,
    decode_concept,
    decode_decision,
    decode_project,
    decode_relationship,
    decode_round,
    decode_trace,
    encode_concept,
    encode_decision,
    encode_project,
    encode_relationship,
    encode_round,
    encode_trace,
    strict_object,
    string_tuple,
)
from .intake import DesignFlowWorkspace
from .model import (
    ConceptStatus,
    ConflictRelation,
    DecisionStatus,
    TraceAction,
)
from .session import DraftRound, SessionRecord, decode_draft, decode_session, encode_draft, encode_session
from .unresolved import compile_unresolved_register


APPLICATION_VERSION = "0.2.0"
PROJECT_FORMAT_VERSION = "0.2.0"
HASH_ALGORITHM = "sha256"
CANONICAL_JSON = "utf-8; sorted-keys; compact-separators; final-newline"

AUTHORITATIVE_ROLES = {
    "manifest.json": "manifest",
    "rounds.json": "round_history",
    "decisions.json": "decision_ledger",
    "concepts.json": "concept_registry",
    "unresolved.json": "unresolved_register",
    "trace.json": "trace",
}
OPERATIONAL_ROLES = {
    "sessions.json": "session_metadata",
    "working/draft.json": "draft_working_state",
    "sources/index.json": "source_evidence_metadata",
}
RESERVED_PATHS = {
    *AUTHORITATIVE_ROLES,
    *OPERATIONAL_ROLES,
    "cache/current_state.json",
    "generated/living_application.md",
    "generated/context_handoff.md",
}


class ProjectValidationError(ValueError):
    """Persisted project material failed before semantic activation."""


class PromotionError(ProjectValidationError):
    """Promotion failed before its explicit candidate-to-target commit point."""

    def __init__(self, message: str, *, preserve_candidate: bool = False) -> None:
        super().__init__(message)
        self.preserve_candidate = preserve_candidate


@dataclass(slots=True, frozen=True)
class FileRegistryEntry:
    path: str
    semantic_role: str
    save_generation: int
    content_hash: str


@dataclass(slots=True, frozen=True)
class ArtifactRegistryEntry:
    path: str
    semantic_role: str
    source_save_generation: int
    compiler_identity: str
    compiler_version: str


@dataclass(slots=True, frozen=True)
class ProjectManifest:
    project_id: str
    project_format_version: str
    application_version: str
    save_generation: int
    project: Mapping[str, JsonValue]
    authoritative_files: tuple[FileRegistryEntry, ...]
    operational_files: tuple[FileRegistryEntry, ...]
    derived_artifacts: tuple[ArtifactRegistryEntry, ...]
    hash_algorithm: str = HASH_ALGORITHM
    canonical_json: str = CANONICAL_JSON
    manifest_hash_mode: str = "canonical-manifest-with-empty-self-hash"

    def file_entry(self, path: str) -> FileRegistryEntry:
        for entry in (*self.authoritative_files, *self.operational_files):
            if entry.path == path:
                return entry
        raise KeyError(path)


@dataclass(slots=True, frozen=True)
class ArtifactContent:
    semantic_role: str
    compiler_identity: str
    compiler_version: str
    content: str


@dataclass(slots=True, frozen=True)
class SourceReference:
    """Non-authoritative evidence metadata; local paths remain project-relative."""

    source_id: str
    label: str
    uri: str | None = None
    local_path: str | None = None

    def __post_init__(self) -> None:
        if self.uri is None and self.local_path is None:
            raise ValueError("A source reference requires a URI or local path")
        if self.local_path is not None:
            path = Path(self.local_path)
            if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("sources",):
                raise ValueError("Local source paths must be project-relative under sources/")


@dataclass(slots=True)
class LoadedProject:
    path: Path
    workspace: DesignFlowWorkspace
    manifest: ProjectManifest
    sessions: tuple[SessionRecord, ...]
    draft: DraftRound | None
    sources: tuple[SourceReference, ...] = ()

    @property
    def save_generation(self) -> int:
        return self.manifest.save_generation

    def artifact_status(self, path: str) -> str:
        entry = next(
            (item for item in self.manifest.derived_artifacts if item.path == path),
            None,
        )
        if entry is None or not (self.path / path).is_file():
            return "MISSING"
        if entry.source_save_generation != self.manifest.save_generation:
            return "STALE"
        return "CURRENT"


def canonical_json_bytes(value: JsonValue) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ProjectValidationError(f"Value is not canonical JSON data: {error}") from error
    return (text + "\n").encode("utf-8")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry_to_data(value: FileRegistryEntry) -> dict[str, JsonValue]:
    return {
        "path": value.path,
        "semantic_role": value.semantic_role,
        "save_generation": value.save_generation,
        "content_hash": value.content_hash,
    }


def _entry_from_data(value: Any, context: str) -> FileRegistryEntry:
    data = strict_object(
        value,
        {"path", "semantic_role", "save_generation", "content_hash"},
        context,
    )
    return FileRegistryEntry(
        path=as_string(data["path"], f"{context}.path"),
        semantic_role=as_string(data["semantic_role"], f"{context}.semantic_role"),
        save_generation=as_int(data["save_generation"], f"{context}.save_generation"),
        content_hash=as_string(data["content_hash"], f"{context}.content_hash"),
    )


def _artifact_to_data(value: ArtifactRegistryEntry) -> dict[str, JsonValue]:
    return {
        "path": value.path,
        "semantic_role": value.semantic_role,
        "source_save_generation": value.source_save_generation,
        "compiler_identity": value.compiler_identity,
        "compiler_version": value.compiler_version,
    }


def _artifact_from_data(value: Any, context: str) -> ArtifactRegistryEntry:
    data = strict_object(
        value,
        {
            "path",
            "semantic_role",
            "source_save_generation",
            "compiler_identity",
            "compiler_version",
        },
        context,
    )
    return ArtifactRegistryEntry(
        path=as_string(data["path"], f"{context}.path"),
        semantic_role=as_string(data["semantic_role"], f"{context}.semantic_role"),
        source_save_generation=as_int(
            data["source_save_generation"], f"{context}.source_save_generation"
        ),
        compiler_identity=as_string(
            data["compiler_identity"], f"{context}.compiler_identity"
        ),
        compiler_version=as_string(
            data["compiler_version"], f"{context}.compiler_version"
        ),
    )


def manifest_to_data(value: ProjectManifest) -> dict[str, JsonValue]:
    return {
        "project_id": value.project_id,
        "project_format_version": value.project_format_version,
        "application_version": value.application_version,
        "save_generation": value.save_generation,
        "project": dict(value.project),
        "authoritative_files": [_entry_to_data(item) for item in value.authoritative_files],
        "operational_files": [_entry_to_data(item) for item in value.operational_files],
        "derived_artifacts": [_artifact_to_data(item) for item in value.derived_artifacts],
        "integrity": {
            "hash_algorithm": value.hash_algorithm,
            "canonical_json": value.canonical_json,
            "manifest_hash_mode": value.manifest_hash_mode,
        },
    }


def manifest_from_data(value: Any) -> ProjectManifest:
    data = strict_object(
        value,
        {
            "project_id",
            "project_format_version",
            "application_version",
            "save_generation",
            "project",
            "authoritative_files",
            "operational_files",
            "derived_artifacts",
            "integrity",
        },
        "manifest",
    )
    integrity = strict_object(
        data["integrity"],
        {"hash_algorithm", "canonical_json", "manifest_hash_mode"},
        "manifest.integrity",
    )
    if type(data["project"]) is not dict:
        raise SchemaError("manifest.project must be an object")
    return ProjectManifest(
        project_id=as_string(data["project_id"], "manifest.project_id"),
        project_format_version=as_string(
            data["project_format_version"], "manifest.project_format_version"
        ),
        application_version=as_string(data["application_version"], "manifest.application_version"),
        save_generation=as_int(data["save_generation"], "manifest.save_generation"),
        project=data["project"],
        authoritative_files=tuple(
            _entry_from_data(item, f"manifest.authoritative_files[{index}]")
            for index, item in enumerate(
                as_list(data["authoritative_files"], "manifest.authoritative_files")
            )
        ),
        operational_files=tuple(
            _entry_from_data(item, f"manifest.operational_files[{index}]")
            for index, item in enumerate(
                as_list(data["operational_files"], "manifest.operational_files")
            )
        ),
        derived_artifacts=tuple(
            _artifact_from_data(item, f"manifest.derived_artifacts[{index}]")
            for index, item in enumerate(
                as_list(data["derived_artifacts"], "manifest.derived_artifacts")
            )
        ),
        hash_algorithm=as_string(integrity["hash_algorithm"], "manifest.integrity.hash_algorithm"),
        canonical_json=as_string(integrity["canonical_json"], "manifest.integrity.canonical_json"),
        manifest_hash_mode=as_string(
            integrity["manifest_hash_mode"], "manifest.integrity.manifest_hash_mode"
        ),
    )


def _envelope(
    *, project_id: str, role: str, generation: int, data: JsonValue
) -> dict[str, JsonValue]:
    return {
        "project_format_version": PROJECT_FORMAT_VERSION,
        "project_id": project_id,
        "semantic_role": role,
        "save_generation": generation,
        "data": data,
    }


def _parse_envelope(
    value: Any,
    *,
    project_id: str,
    role: str,
    generation: int,
    context: str,
) -> JsonValue:
    data = strict_object(
        value,
        {"project_format_version", "project_id", "semantic_role", "save_generation", "data"},
        context,
    )
    if as_string(data["project_format_version"], f"{context}.project_format_version") != PROJECT_FORMAT_VERSION:
        raise ProjectValidationError(f"{context} has unsupported project_format_version")
    if as_string(data["project_id"], f"{context}.project_id") != project_id:
        raise ProjectValidationError(f"{context} belongs to a different project")
    if as_string(data["semantic_role"], f"{context}.semantic_role") != role:
        raise ProjectValidationError(f"{context} declares the wrong semantic role")
    if as_int(data["save_generation"], f"{context}.save_generation") != generation:
        raise ProjectValidationError(f"{context} has mixed save_generation")
    return data["data"]


def _read_canonical_json(path: Path, context: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ProjectValidationError(f"Cannot read {context}: {error}") from error
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectValidationError(f"{context} is not valid UTF-8 JSON: {error}") from error
    if type(value) is not dict:
        raise ProjectValidationError(f"{context} must contain a JSON object")
    if raw != canonical_json_bytes(value):
        raise ProjectValidationError(f"{context} is not canonical JSON")
    return value, raw


def _safe_registered_path(root: Path, path: str) -> Path:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts or path.replace("\\", "/") != path:
        raise ProjectValidationError(f"Manifest path is not project-relative: {path}")
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ProjectValidationError(f"Manifest path escapes project directory: {path}")
    return resolved


def _manifest_projection(value: ProjectManifest) -> ProjectManifest:
    entries = tuple(
        replace(item, content_hash="") if item.path == "manifest.json" else item
        for item in value.authoritative_files
    )
    return replace(value, authoritative_files=entries)


def _workspace_payloads(
    workspace: DesignFlowWorkspace, generation: int
) -> dict[str, dict[str, JsonValue]]:
    project_id = workspace.project.project_id
    return {
        "rounds.json": _envelope(
            project_id=project_id,
            role=AUTHORITATIVE_ROLES["rounds.json"],
            generation=generation,
            data={"rounds": [encode_round(item) for item in workspace.rounds.rounds]},
        ),
        "decisions.json": _envelope(
            project_id=project_id,
            role=AUTHORITATIVE_ROLES["decisions.json"],
            generation=generation,
            data={
                "decisions": [encode_decision(item) for item in workspace.ledger.decisions],
                "relationships": [
                    encode_relationship(item) for item in workspace.ledger.relationships
                ],
            },
        ),
        "concepts.json": _envelope(
            project_id=project_id,
            role=AUTHORITATIVE_ROLES["concepts.json"],
            generation=generation,
            data={
                "current": [encode_concept(item) for item in workspace.concepts.concepts],
                "affected": [encode_concept(item) for item in workspace.concepts.affected],
                "history": [encode_concept(item) for item in workspace.concepts.history],
            },
        ),
        "unresolved.json": _envelope(
            project_id=project_id,
            role=AUTHORITATIVE_ROLES["unresolved.json"],
            generation=generation,
            data={"items": list(compile_unresolved_register(workspace))},
        ),
        "trace.json": _envelope(
            project_id=project_id,
            role=AUTHORITATIVE_ROLES["trace.json"],
            generation=generation,
            data={"records": [encode_trace(item) for item in workspace.trace.records]},
        ),
    }


def _operational_payloads(
    project_id: str,
    generation: int,
    sessions: tuple[SessionRecord, ...],
    draft: DraftRound | None,
    sources: tuple[SourceReference, ...],
) -> dict[str, dict[str, JsonValue]]:
    return {
        "sessions.json": _envelope(
            project_id=project_id,
            role=OPERATIONAL_ROLES["sessions.json"],
            generation=generation,
            data={"sessions": [encode_session(item) for item in sessions]},
        ),
        "working/draft.json": _envelope(
            project_id=project_id,
            role=OPERATIONAL_ROLES["working/draft.json"],
            generation=generation,
            data={"draft": encode_draft(draft) if draft is not None else None},
        ),
        "sources/index.json": _envelope(
            project_id=project_id,
            role=OPERATIONAL_ROLES["sources/index.json"],
            generation=generation,
            data={
                "sources": [
                    {
                        "source_id": item.source_id,
                        "label": item.label,
                        "uri": item.uri,
                        "local_path": item.local_path,
                    }
                    for item in sources
                ]
            },
        ),
    }


def _current_state_data(workspace: DesignFlowWorkspace, generation: int) -> dict[str, JsonValue]:
    state = workspace.state_compiler.compile(workspace.project, workspace.ledger)
    return {
        "source_save_generation": generation,
        "compiler_identity": "design_flow.current_state",
        "compiler_version": APPLICATION_VERSION,
        "data": {
            "project_id": state.project_id,
            "version": state.version,
            "decisions": [encode_decision(item) for item in state.decisions],
            "unresolved": list(state.unresolved),
        },
    }


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _artifact_bytes(content: ArtifactContent, generation: int) -> bytes:
    metadata = {
        "source_save_generation": generation,
        "compiler_identity": content.compiler_identity,
        "compiler_version": content.compiler_version,
        "semantic_role": content.semantic_role,
    }
    header = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    return f"<!-- design-flow-artifact {header} -->\n\n{content.content.rstrip()}\n".encode("utf-8")


class ProjectStore:
    """Save and load complete projects through a strict activation boundary."""

    def __init__(self) -> None:
        self.last_recovery_warning: str | None = None

    def create(
        self,
        path: str | Path,
        workspace: DesignFlowWorkspace,
        *,
        sessions: tuple[SessionRecord, ...] = (),
        draft: DraftRound | None = None,
        sources: tuple[SourceReference, ...] = (),
    ) -> LoadedProject:
        target = Path(path).resolve()
        if target.exists() and any(target.iterdir()):
            raise FileExistsError(f"Project directory is not empty: {target}")
        if target.exists():
            target.rmdir()
        self.save(
            target,
            workspace,
            sessions=sessions,
            draft=draft,
            sources=sources,
            prior_manifest=None,
        )
        return self.load(target)

    def save(
        self,
        path: str | Path,
        workspace: DesignFlowWorkspace,
        *,
        sessions: tuple[SessionRecord, ...] = (),
        draft: DraftRound | None = None,
        sources: tuple[SourceReference, ...] = (),
        artifacts: Mapping[str, ArtifactContent] | None = None,
        prior_manifest: ProjectManifest | None = None,
    ) -> ProjectManifest:
        self.last_recovery_warning = None
        target = Path(path).resolve()
        if prior_manifest is None and target.exists():
            prior_manifest = self._read_manifest(target)
        generation = 1 if prior_manifest is None else prior_manifest.save_generation + 1
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        candidate = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.candidate-", dir=parent)
        )
        promoted = False
        preserve_candidate = False
        try:
            if target.exists():
                shutil.copytree(target, candidate, dirs_exist_ok=True)
            for reserved in (candidate / "cache", candidate / "generated", candidate / "working"):
                if reserved.exists() and not reserved.is_dir():
                    raise ProjectValidationError(f"Reserved path must be a directory: {reserved.name}")

            file_bytes: dict[str, bytes] = {}
            for relative, value in _workspace_payloads(workspace, generation).items():
                file_bytes[relative] = canonical_json_bytes(value)
            for relative, value in _operational_payloads(
                workspace.project.project_id, generation, sessions, draft, sources
            ).items():
                file_bytes[relative] = canonical_json_bytes(value)
            for relative, data in file_bytes.items():
                _write_bytes(candidate / relative, data)

            _write_bytes(
                candidate / "cache/current_state.json",
                canonical_json_bytes(_current_state_data(workspace, generation)),
            )

            artifact_entries: list[ArtifactRegistryEntry] = []
            if prior_manifest is not None:
                artifact_entries.extend(prior_manifest.derived_artifacts)
            if artifacts:
                by_path = {item.path: item for item in artifact_entries}
                for relative, content in artifacts.items():
                    if relative not in {
                        "generated/living_application.md",
                        "generated/context_handoff.md",
                    }:
                        raise ProjectValidationError(f"Unsupported generated artifact path: {relative}")
                    _write_bytes(candidate / relative, _artifact_bytes(content, generation))
                    by_path[relative] = ArtifactRegistryEntry(
                        path=relative,
                        semantic_role=content.semantic_role,
                        source_save_generation=generation,
                        compiler_identity=content.compiler_identity,
                        compiler_version=content.compiler_version,
                    )
                artifact_entries = [by_path[key] for key in sorted(by_path)]

            authoritative_entries = tuple(
                FileRegistryEntry(
                    path=relative,
                    semantic_role=role,
                    save_generation=generation,
                    content_hash=("" if relative == "manifest.json" else content_hash(file_bytes[relative])),
                )
                for relative, role in AUTHORITATIVE_ROLES.items()
            )
            operational_entries = tuple(
                FileRegistryEntry(
                    path=relative,
                    semantic_role=role,
                    save_generation=generation,
                    content_hash=content_hash(file_bytes[relative]),
                )
                for relative, role in OPERATIONAL_ROLES.items()
            )
            manifest = ProjectManifest(
                project_id=workspace.project.project_id,
                project_format_version=PROJECT_FORMAT_VERSION,
                application_version=APPLICATION_VERSION,
                save_generation=generation,
                project=encode_project(workspace.project),
                authoritative_files=authoritative_entries,
                operational_files=operational_entries,
                derived_artifacts=tuple(artifact_entries),
            )
            self_hash = content_hash(canonical_json_bytes(manifest_to_data(_manifest_projection(manifest))))
            manifest = replace(
                manifest,
                authoritative_files=tuple(
                    replace(item, content_hash=self_hash)
                    if item.path == "manifest.json"
                    else item
                    for item in manifest.authoritative_files
                ),
            )
            _write_bytes(candidate / "manifest.json", canonical_json_bytes(manifest_to_data(manifest)))

            self.load(candidate, check_recovery=False, regenerate_cache=False)
            self.last_recovery_warning = self._promote(candidate, target)
            promoted = True
            return manifest
        except PromotionError as error:
            preserve_candidate = error.preserve_candidate
            raise
        finally:
            if not promoted and not preserve_candidate and candidate.exists():
                shutil.rmtree(candidate, ignore_errors=True)

    def load(
        self,
        path: str | Path,
        *,
        check_recovery: bool = True,
        regenerate_cache: bool = True,
    ) -> LoadedProject:
        """Reject all decode/semantic failures through one activation error type."""

        try:
            return self._load_project(
                path,
                check_recovery=check_recovery,
                regenerate_cache=regenerate_cache,
            )
        except ProjectValidationError:
            raise
        except (KeyError, OSError, SchemaError, TypeError, ValueError) as error:
            raise ProjectValidationError(f"Semantic activation rejected: {error}") from error

    def _load_project(
        self,
        path: str | Path,
        *,
        check_recovery: bool = True,
        regenerate_cache: bool = True,
    ) -> LoadedProject:
        root = Path(path).resolve()
        if check_recovery:
            self._check_recovery_state(root)
        manifest = self._read_manifest(root)
        self._validate_manifest_contract(manifest)
        raw_files = self._verify_registered_files(root, manifest)

        project = decode_project(manifest.project_id, manifest.project)
        generation = manifest.save_generation
        parsed: dict[str, JsonValue] = {}
        for relative, role in {**AUTHORITATIVE_ROLES, **OPERATIONAL_ROLES}.items():
            if relative == "manifest.json":
                continue
            value = json.loads(raw_files[relative].decode("utf-8"))
            parsed[relative] = _parse_envelope(
                value,
                project_id=manifest.project_id,
                role=role,
                generation=generation,
                context=relative,
            )

        trace_data = strict_object(parsed["trace.json"], {"records"}, "trace.json.data")
        trace_records = tuple(
            decode_trace(item, f"trace.json.data.records[{index}]")
            for index, item in enumerate(as_list(trace_data["records"], "trace.json.data.records"))
        )
        rounds_data = strict_object(parsed["rounds.json"], {"rounds"}, "rounds.json.data")
        rounds = tuple(
            decode_round(item, f"rounds.json.data.rounds[{index}]")
            for index, item in enumerate(as_list(rounds_data["rounds"], "rounds.json.data.rounds"))
        )
        decisions_data = strict_object(
            parsed["decisions.json"], {"decisions", "relationships"}, "decisions.json.data"
        )
        decisions = tuple(
            decode_decision(item, f"decisions.json.data.decisions[{index}]")
            for index, item in enumerate(
                as_list(decisions_data["decisions"], "decisions.json.data.decisions")
            )
        )
        relationships = tuple(
            decode_relationship(item, f"decisions.json.data.relationships[{index}]")
            for index, item in enumerate(
                as_list(decisions_data["relationships"], "decisions.json.data.relationships")
            )
        )
        concepts_data = strict_object(
            parsed["concepts.json"], {"current", "affected", "history"}, "concepts.json.data"
        )
        concept_groups = {
            key: tuple(
                decode_concept(item, f"concepts.json.data.{key}[{index}]")
                for index, item in enumerate(
                    as_list(concepts_data[key], f"concepts.json.data.{key}")
                )
            )
            for key in ("current", "affected", "history")
        }
        workspace = DesignFlowWorkspace.restore(
            project=project,
            trace_records=trace_records,
            rounds=rounds,
            decisions=decisions,
            relationships=relationships,
            current_concepts=concept_groups["current"],
            affected_concepts=concept_groups["affected"],
            concept_history=concept_groups["history"],
        )
        unresolved_data = strict_object(
            parsed["unresolved.json"], {"items"}, "unresolved.json.data"
        )
        persisted_unresolved = string_tuple(
            unresolved_data["items"], "unresolved.json.data.items"
        )
        self._validate_workspace(workspace, persisted_unresolved)

        sessions_data = strict_object(
            parsed["sessions.json"], {"sessions"}, "sessions.json.data"
        )
        sessions = tuple(
            decode_session(item, f"sessions.json.data.sessions[{index}]")
            for index, item in enumerate(
                as_list(sessions_data["sessions"], "sessions.json.data.sessions")
            )
        )
        if any(item.project_id != project.project_id for item in sessions):
            raise ProjectValidationError("Session metadata belongs to another project")
        if len({item.session_id for item in sessions}) != len(sessions):
            raise ProjectValidationError("Session identifiers must be unique")
        draft_data = strict_object(
            parsed["working/draft.json"], {"draft"}, "working/draft.json.data"
        )
        draft = (
            None
            if draft_data["draft"] is None
            else decode_draft(draft_data["draft"], "working/draft.json.data.draft")
        )
        known_rounds = {item.round_id for item in workspace.rounds.rounds}
        working_rounds = {draft.round_id} if draft is not None else set()
        for session in sessions:
            touched = set(session.rounds_touched)
            committed = set(session.rounds_committed)
            if touched - (known_rounds | working_rounds):
                raise ProjectValidationError(
                    f"Session {session.session_id} touches unknown rounds"
                )
            if committed - known_rounds:
                raise ProjectValidationError(
                    f"Session {session.session_id} commits unknown rounds"
                )
            if committed - touched:
                raise ProjectValidationError(
                    f"Session {session.session_id} committed rounds it never touched"
                )
            if any(
                generation < 1 or generation > manifest.save_generation
                for generation in session.save_generations
            ):
                raise ProjectValidationError(
                    f"Session {session.session_id} has invalid save generations"
                )
            if tuple(sorted(set(session.save_generations))) != session.save_generations:
                raise ProjectValidationError(
                    f"Session {session.session_id} save generations must be unique/increasing"
                )
        if sum(item.ended_at is None for item in sessions) > 1:
            raise ProjectValidationError("At most one persisted session may remain open")
        source_data = strict_object(
            parsed["sources/index.json"], {"sources"}, "sources/index.json.data"
        )
        sources: list[SourceReference] = []
        for index, value in enumerate(
            as_list(source_data["sources"], "sources/index.json.data.sources")
        ):
            context = f"sources/index.json.data.sources[{index}]"
            item = strict_object(
                value, {"source_id", "label", "uri", "local_path"}, context
            )
            uri = item["uri"]
            local_path = item["local_path"]
            if uri is not None and type(uri) is not str:
                raise SchemaError(f"{context}.uri must be a string or null")
            if local_path is not None and type(local_path) is not str:
                raise SchemaError(f"{context}.local_path must be a string or null")
            sources.append(
                SourceReference(
                    source_id=as_string(item["source_id"], f"{context}.source_id"),
                    label=as_string(item["label"], f"{context}.label"),
                    uri=uri,
                    local_path=local_path,
                )
            )
        if len({item.source_id for item in sources}) != len(sources):
            raise ProjectValidationError("Source identifiers must be unique")
        loaded = LoadedProject(root, workspace, manifest, sessions, draft, tuple(sources))
        if regenerate_cache and self._cache_is_stale(root, loaded):
            try:
                _write_bytes(
                    root / "cache/current_state.json",
                    canonical_json_bytes(_current_state_data(workspace, generation)),
                )
            except OSError:
                # Cache repair is best-effort after semantic activation; it is not authority.
                pass
        return loaded

    def clone_workspace(self, workspace: DesignFlowWorkspace) -> DesignFlowWorkspace:
        """Reconstruct an isolated candidate through the same plain-data codecs."""

        generation = 1
        payloads = _workspace_payloads(workspace, generation)
        trace_data = strict_object(
            payloads["trace.json"]["data"], {"records"}, "clone.trace"
        )
        rounds_data = strict_object(
            payloads["rounds.json"]["data"], {"rounds"}, "clone.rounds"
        )
        decisions_data = strict_object(
            payloads["decisions.json"]["data"],
            {"decisions", "relationships"},
            "clone.decisions",
        )
        concepts_data = strict_object(
            payloads["concepts.json"]["data"],
            {"current", "affected", "history"},
            "clone.concepts",
        )
        return DesignFlowWorkspace.restore(
            project=decode_project(workspace.project.project_id, encode_project(workspace.project)),
            trace_records=tuple(
                decode_trace(item, f"clone.trace[{index}]")
                for index, item in enumerate(as_list(trace_data["records"], "clone.trace.records"))
            ),
            rounds=tuple(
                decode_round(item, f"clone.rounds[{index}]")
                for index, item in enumerate(as_list(rounds_data["rounds"], "clone.rounds.rounds"))
            ),
            decisions=tuple(
                decode_decision(item, f"clone.decisions[{index}]")
                for index, item in enumerate(
                    as_list(decisions_data["decisions"], "clone.decisions.decisions")
                )
            ),
            relationships=tuple(
                decode_relationship(item, f"clone.relationships[{index}]")
                for index, item in enumerate(
                    as_list(decisions_data["relationships"], "clone.decisions.relationships")
                )
            ),
            current_concepts=tuple(
                decode_concept(item, f"clone.current[{index}]")
                for index, item in enumerate(
                    as_list(concepts_data["current"], "clone.concepts.current")
                )
            ),
            affected_concepts=tuple(
                decode_concept(item, f"clone.affected[{index}]")
                for index, item in enumerate(
                    as_list(concepts_data["affected"], "clone.concepts.affected")
                )
            ),
            concept_history=tuple(
                decode_concept(item, f"clone.history[{index}]")
                for index, item in enumerate(
                    as_list(concepts_data["history"], "clone.concepts.history")
                )
            ),
        )

    def _read_manifest(self, root: Path) -> ProjectManifest:
        if not root.is_dir():
            raise ProjectValidationError(f"Project directory does not exist: {root}")
        value, _ = _read_canonical_json(root / "manifest.json", "manifest.json")
        try:
            return manifest_from_data(value)
        except (SchemaError, TypeError, ValueError) as error:
            raise ProjectValidationError(f"Invalid manifest: {error}") from error

    def _validate_manifest_contract(self, manifest: ProjectManifest) -> None:
        if manifest.project_format_version != PROJECT_FORMAT_VERSION:
            raise ProjectValidationError(
                f"Unsupported project_format_version: {manifest.project_format_version}"
            )
        if manifest.hash_algorithm != HASH_ALGORITHM:
            raise ProjectValidationError(f"Unsupported hash algorithm: {manifest.hash_algorithm}")
        if manifest.canonical_json != CANONICAL_JSON:
            raise ProjectValidationError("Unsupported canonical JSON contract")
        if manifest.manifest_hash_mode != "canonical-manifest-with-empty-self-hash":
            raise ProjectValidationError("Unsupported manifest hash mode")
        if manifest.save_generation < 1:
            raise ProjectValidationError("save_generation must be positive")
        auth = {item.path: item.semantic_role for item in manifest.authoritative_files}
        operations = {item.path: item.semantic_role for item in manifest.operational_files}
        if auth != AUTHORITATIVE_ROLES:
            raise ProjectValidationError("Authoritative file registry is incomplete or incorrect")
        if operations != OPERATIONAL_ROLES:
            raise ProjectValidationError("Operational file registry is incomplete or incorrect")
        all_entries = (*manifest.authoritative_files, *manifest.operational_files)
        if len({item.path for item in all_entries}) != len(all_entries):
            raise ProjectValidationError("File registry paths must be unique")
        if any(item.save_generation != manifest.save_generation for item in all_entries):
            raise ProjectValidationError("Manifest contains mixed save_generation entries")
        if any(item.path not in RESERVED_PATHS for item in all_entries):
            raise ProjectValidationError("Manifest registers an unsupported reserved path")

    def _verify_registered_files(
        self, root: Path, manifest: ProjectManifest
    ) -> dict[str, bytes]:
        raw: dict[str, bytes] = {}
        for entry in (*manifest.authoritative_files, *manifest.operational_files):
            path = _safe_registered_path(root, entry.path)
            if not path.is_file():
                raise ProjectValidationError(f"Missing registered file: {entry.path}")
            value, data = _read_canonical_json(path, entry.path)
            raw[entry.path] = data
            if entry.path == "manifest.json":
                expected = content_hash(
                    canonical_json_bytes(manifest_to_data(_manifest_projection(manifest)))
                )
            else:
                expected = content_hash(data)
            if entry.content_hash != expected:
                raise ProjectValidationError(f"Hash mismatch for {entry.path}")
        return raw

    def _validate_workspace(
        self,
        workspace: DesignFlowWorkspace,
        persisted_unresolved: tuple[str, ...],
    ) -> None:
        trace_ids = {item.trace_id for item in workspace.trace.records}
        project_events = [
            item
            for item in workspace.trace.records
            if item.action is TraceAction.REGISTER_PROJECT
            and item.entity_id == workspace.project.project_id
        ]
        if len(project_events) != 1:
            raise ProjectValidationError("TRACE must contain one matching project registration")
        project_event = project_events[0]
        if (
            project_event.entity_type != "project"
            or project_event.details.get("name") != workspace.project.name
            or project_event.details.get("mode") != workspace.project.current_mode.value
            or project_event.details.get("authority") != workspace.project.authority
        ):
            raise ProjectValidationError("Project registration TRACE disagrees with project metadata")
        round_ids = {item.round_id for item in workspace.rounds.rounds}
        question_index: dict[tuple[str, str], Any] = {}
        for design_round in workspace.rounds.rounds:
            if any(ref not in trace_ids for ref in design_round.trace_refs):
                raise ProjectValidationError(f"Round {design_round.round_id} has invalid TRACE refs")
            round_events = [
                workspace.trace.get(ref)
                for ref in design_round.trace_refs
                if workspace.trace.get(ref).action is TraceAction.REGISTER_ROUND
            ]
            if not any(
                item.entity_type == "round"
                and item.entity_id == design_round.round_id
                and item.details.get("topic") == design_round.topic
                and item.details.get("purpose") == design_round.purpose
                and item.details.get("prerequisites") == design_round.prerequisites
                and item.details.get("mode") == workspace.project.current_mode.value
                for item in round_events
            ):
                raise ProjectValidationError(
                    f"Round {design_round.round_id} lacks matching registration TRACE"
                )
            question_ids: set[str] = set()
            for question in design_round.questions:
                if question.question_id in question_ids:
                    raise ProjectValidationError(
                        f"Round {design_round.round_id} repeats question {question.question_id}"
                    )
                question_ids.add(question.question_id)
                question_index[(design_round.round_id, question.question_id)] = question
                if any(ref not in trace_ids for ref in question.trace_refs):
                    raise ProjectValidationError(
                        f"Question {question.question_id} has invalid TRACE refs"
                    )
                question_events = [workspace.trace.get(ref) for ref in question.trace_refs]
                if not any(
                    item.action is TraceAction.REGISTER_QUESTION
                    and item.entity_type == "question"
                    and item.entity_id == question.question_id
                    and item.details.get("round_id") == design_round.round_id
                    and item.details.get("question_type") == question.question_type.value
                    and item.details.get("question_text") == question.text
                    and item.details.get("options")
                    == tuple((option.key, option.label) for option in question.options)
                    for item in question_events
                ):
                    raise ProjectValidationError(
                        f"Question {question.question_id} lacks matching registration TRACE"
                    )
                if not any(
                    item.action is TraceAction.RECOMMEND
                    and item.entity_id == question.question_id
                    and item.details.get("proposed_answer")
                    == tuple(question.recommendation.proposed_answer)
                    and item.details.get("reason") == question.recommendation.reason
                    and item.details.get("status") == question.recommendation.status.value
                    for item in question_events
                ):
                    raise ProjectValidationError(
                        f"Question {question.question_id} recommendation disagrees with TRACE"
                    )
                recorded = design_round.owner_answer_set.get(question.question_id)
                if question.owner_answer != recorded:
                    raise ProjectValidationError(
                        f"Owner-answer history disagrees for {question.question_id}"
                    )
                if recorded is not None:
                    if (
                        recorded.source_round != design_round.round_id
                        or recorded.source_question != question.question_id
                        or question.answer_status is not recorded.status
                    ):
                        raise ProjectValidationError(
                            f"Owner answer source/status disagrees for {question.question_id}"
                        )
                    if not any(
                        item.action is TraceAction.OWNER_SELECT
                        and item.entity_id == question.question_id
                        and item.details.get("raw_value") == recorded.raw_value
                        and item.details.get("normalized_value")
                        == tuple(recorded.normalized_value)
                        and item.details.get("qualifiers") == tuple(recorded.qualifiers)
                        and item.details.get("status") == recorded.status.value
                        for item in question_events
                    ):
                        raise ProjectValidationError(
                            f"Owner answer for {question.question_id} disagrees with TRACE"
                        )
            if set(design_round.owner_answer_set) - question_ids:
                raise ProjectValidationError(
                    f"Round {design_round.round_id} has answers for unknown questions"
                )
            if design_round.conflicts_detected:
                raise ProjectValidationError(
                    f"Round {design_round.round_id} has non-authoritative conflict projection data"
                )

        decisions = {item.decision_id: item for item in workspace.ledger.decisions}
        synthesis_by_round: dict[str, list[str]] = {
            round_id: [] for round_id in round_ids
        }
        for decision in workspace.ledger.decisions:
            question = question_index.get((decision.source_round, decision.source_question))
            if question is None or question.owner_answer is None:
                raise ProjectValidationError(
                    f"Decision {decision.decision_id} has an invalid round/question source"
                )
            if question.owner_answer.normalized_value != decision.authoritative_value:
                raise ProjectValidationError(
                    f"Decision {decision.decision_id} disagrees with its owner answer"
                )
            answer = question.owner_answer
            provenance = decision.provenance
            if (
                provenance.recommendation_was != question.recommendation.proposed_answer
                or provenance.recommendation_reason != question.recommendation.reason
                or provenance.owner_raw_value != answer.raw_value
                or provenance.owner_normalized_value != answer.normalized_value
                or provenance.owner_qualifiers != answer.qualifiers
                or provenance.question_text != question.text
                or provenance.options != question.options
                or provenance.rule_source_value != decision.authoritative_value
            ):
                raise ProjectValidationError(
                    f"Decision {decision.decision_id} provenance disagrees with round history"
                )
            try:
                workspace.trace.validate_registered_decision(decision)
            except ValueError as error:
                raise ProjectValidationError(str(error)) from error
            synthesis_by_round[decision.source_round].append(decision.canonical_rule)

        for design_round in workspace.rounds.rounds:
            expected_synthesis = tuple(synthesis_by_round[design_round.round_id])
            if design_round.synthesis != expected_synthesis:
                raise ProjectValidationError(
                    f"Round {design_round.round_id} synthesis disagrees with registered decisions"
                )
            if design_round.derived_rules != expected_synthesis:
                raise ProjectValidationError(
                    f"Round {design_round.round_id} derived rules disagree with registered decisions"
                )

        supersession_edges: dict[str, list[str]] = {}
        direct_supersessions: list[tuple[str, str]] = []
        for relation in workspace.ledger.relationships:
            if relation.earlier_decision not in decisions or relation.later_decision not in decisions:
                raise ProjectValidationError("Decision relationship references an unknown decision")
            if relation.relation is ConflictRelation.SUPERSEDES:
                edge = (relation.earlier_decision, relation.later_decision)
                if edge in direct_supersessions:
                    raise ProjectValidationError(
                        f"Duplicate SUPERSEDES relationship: {edge[0]} -> {edge[1]}"
                    )
                if any(earlier == edge[0] for earlier, _ in direct_supersessions):
                    raise ProjectValidationError(
                        f"Decision {edge[0]} has multiple direct replacements"
                    )
                direct_supersessions.append(edge)
                earlier = decisions[relation.earlier_decision]
                later = decisions[relation.later_decision]
                if earlier.status is not DecisionStatus.SUPERSEDED:
                    raise ProjectValidationError("SUPERSEDES relation has a non-historical predecessor")
                if earlier.decision_id not in later.supersedes:
                    raise ProjectValidationError("SUPERSEDES lineage disagrees with relationship ledger")
                events = [
                    item.action is TraceAction.SUPERSEDE
                    and item.entity_id == earlier.decision_id
                    and item.details.get("replaced_by") == later.decision_id
                    for item in workspace.trace.records
                ]
                matching_trace = tuple(
                    item.trace_id
                    for item, matches in zip(workspace.trace.records, events)
                    if matches
                )
                if len(matching_trace) != 1:
                    raise ProjectValidationError("SUPERSEDES relationship lacks matching TRACE")
                trace_id = matching_trace[0]
                if trace_id not in earlier.trace_refs or trace_id not in later.trace_refs:
                    raise ProjectValidationError(
                        "SUPERSEDES relationship TRACE is not bound to both decisions"
                    )
                supersession_edges.setdefault(earlier.decision_id, []).append(later.decision_id)
        self._reject_cycles(supersession_edges)

        outgoing = {earlier: later for earlier, later in direct_supersessions}
        for decision in workspace.ledger.decisions:
            if decision.status is DecisionStatus.SUPERSEDED and decision.decision_id not in outgoing:
                raise ProjectValidationError(
                    f"SUPERSEDED decision {decision.decision_id} has no replacement relationship"
                )

        incoming: dict[str, list[str]] = {}
        for earlier, later in direct_supersessions:
            incoming.setdefault(later, []).append(earlier)

        def canonical_ancestry(decision_id: str) -> tuple[str, ...]:
            ancestry: list[str] = []
            for predecessor in incoming.get(decision_id, []):
                for item in (*canonical_ancestry(predecessor), predecessor):
                    if item not in ancestry:
                        ancestry.append(item)
            return tuple(ancestry)

        for decision in workspace.ledger.decisions:
            expected = canonical_ancestry(decision.decision_id)
            if decision.supersedes != expected:
                raise ProjectValidationError(
                    f"Decision {decision.decision_id} supersedes ancestry disagrees with graph: "
                    f"expected {expected}, got {decision.supersedes}"
                )

        relationship_edges = set(direct_supersessions)
        for event in workspace.trace.records:
            if event.action is not TraceAction.SUPERSEDE:
                continue
            replacement = event.details.get("replaced_by")
            if type(replacement) is not str or (event.entity_id, replacement) not in relationship_edges:
                raise ProjectValidationError(
                    f"Orphaned SUPERSEDE TRACE event: {event.trace_id}"
                )

        for group_name, group in (
            ("current", workspace.concepts.concepts),
            ("affected", workspace.concepts.affected),
            ("history", workspace.concepts.history),
        ):
            for concept in group:
                if any(ref not in trace_ids for ref in concept.trace_refs):
                    raise ProjectValidationError(f"Concept {concept.concept_id} has invalid TRACE refs")
                if any(item not in decisions for item in concept.source_decisions):
                    raise ProjectValidationError(
                        f"Concept {concept.concept_id} references an unknown decision"
                    )
                current_source = concept.provenance.get("current_source")
                if not isinstance(current_source, Mapping):
                    raise ProjectValidationError(
                        f"Concept {concept.concept_id} has invalid provenance"
                    )
                source_id = current_source.get("source_decision")
                if source_id not in decisions:
                    raise ProjectValidationError(
                        f"Concept {concept.concept_id} has an unknown current source"
                    )
                source_decision = decisions[source_id]
                synthesis = workspace.trace.validate_registered_decision(source_decision)
                expected_source = {
                    "source_decision": source_decision.decision_id,
                    "source_round": source_decision.source_round,
                    "source_question": source_decision.source_question,
                    "owner_answer": tuple(source_decision.authoritative_value),
                    "recommendation_was": tuple(
                        source_decision.provenance.recommendation_was
                    ),
                    "trace_ref": synthesis.trace_id,
                }
                if dict(current_source) != expected_source:
                    raise ProjectValidationError(
                        f"Concept {concept.concept_id} current provenance disagrees with its decision"
                    )
                concept_events = [workspace.trace.get(ref) for ref in concept.trace_refs]
                if not any(
                    item.entity_id == concept.concept_id
                    and item.action
                    in {
                        TraceAction.REGISTER_CONCEPT,
                        TraceAction.REVISE_CONCEPT,
                        TraceAction.MARK_CONCEPT_AFFECTED,
                        TraceAction.DEPRECATE_CONCEPT,
                    }
                    for item in concept_events
                ):
                    raise ProjectValidationError(
                        f"Concept {concept.concept_id} lacks lifecycle TRACE"
                    )
                if group_name == "current" and decisions[source_id].status is DecisionStatus.SUPERSEDED:
                    raise ProjectValidationError(
                        f"Current concept {concept.concept_id} has a superseded source"
                    )
                expected_statuses = {
                    "current": {ConceptStatus.CURRENT},
                    "affected": {ConceptStatus.UNRESOLVED},
                    "history": {ConceptStatus.SUPERSEDED, ConceptStatus.DEPRECATED},
                }
                if concept.status not in expected_statuses[group_name]:
                    raise ProjectValidationError(
                        f"Concept {concept.concept_id} is in the wrong registry partition"
                    )

        if persisted_unresolved != compile_unresolved_register(workspace):
            raise ProjectValidationError("Persisted unresolved register disagrees with semantic state")
        workspace.state_compiler.compile(workspace.project, workspace.ledger)

    @staticmethod
    def _reject_cycles(edges: Mapping[str, list[str]]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ProjectValidationError("Supersession graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for child in edges.get(node, []):
                visit(child)
            visiting.remove(node)
            visited.add(node)

        for node in edges:
            visit(node)

    def _cache_is_stale(self, root: Path, loaded: LoadedProject) -> bool:
        path = root / "cache/current_state.json"
        if not path.is_file():
            return True
        try:
            value, _ = _read_canonical_json(path, "cache/current_state.json")
            data = strict_object(
                value,
                {"source_save_generation", "compiler_identity", "compiler_version", "data"},
                "cache/current_state.json",
            )
            return (
                as_int(data["source_save_generation"], "cache.source_save_generation")
                != loaded.manifest.save_generation
                or data["compiler_identity"] != "design_flow.current_state"
                or data["compiler_version"] != APPLICATION_VERSION
            )
        except (ProjectValidationError, SchemaError, ValueError, TypeError):
            return True

    def _check_recovery_state(self, root: Path) -> None:
        parent = root.parent
        leftovers = sorted(
            [
                *parent.glob(f".{root.name}.candidate-*"),
                *parent.glob(f".{root.name}.backup-*"),
            ]
        )
        if leftovers:
            names = ", ".join(item.name for item in leftovers)
            raise ProjectValidationError(
                f"Interrupted save artifacts require owner review before activation: {names}"
            )

    def _promote(self, candidate: Path, target: Path) -> str | None:
        """Promote at candidate-to-target rename; cleanup is post-commit recovery work."""

        backup = target.parent / f".{target.name}.backup-{uuid4().hex}"
        if not target.exists():
            try:
                os.replace(candidate, target)
            except OSError as error:
                raise PromotionError(
                    f"Candidate promotion failed before commit: {error}"
                ) from error
            return None
        try:
            os.replace(target, backup)
        except OSError as error:
            raise PromotionError(
                f"Target-to-backup rename failed before commit: {error}"
            ) from error
        try:
            os.replace(candidate, target)
        except OSError as promotion_error:
            try:
                os.replace(backup, target)
            except OSError as rollback_error:
                raise PromotionError(
                    "Candidate promotion failed before commit and prior-state rollback "
                    f"also failed; recovery artifacts preserved: {promotion_error}; "
                    f"rollback: {rollback_error}",
                    preserve_candidate=True,
                ) from rollback_error
            raise PromotionError(
                f"Candidate promotion failed before commit; prior target restored: "
                f"{promotion_error}"
            ) from promotion_error

        # Commit point: candidate now owns the canonical target path.
        try:
            shutil.rmtree(backup)
        except OSError as error:
            return (
                "Storage promotion committed, but backup cleanup failed; "
                f"future ordinary activation requires recovery review: {backup.name}: {error}"
            )
        return None
