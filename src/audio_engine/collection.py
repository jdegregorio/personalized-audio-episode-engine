"""Capability-neutral collection selection and deterministic dossier recording."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from audio_engine.artifacts import (
    ArtifactReference,
    CollectionMethod,
    CollectionRequest,
    CollectionValidationState,
    EvidenceDossier,
)
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseError, LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    load_run_state,
    record_collection_validation,
    refresh_run_summary,
)
from audio_engine.profile import ProfileError, load_profile
from audio_engine.safety import SafetyError, resolve_within_roots
from audio_engine.storage import StorageError, sha256_file
from audio_engine.validation import (
    ValidationReport,
    load_artifact_file,
    validate_artifact_data,
    validate_dossier_against_request,
)

COLLECTION_PROMPT_VERSION = "1.0.0"
NATIVE_RESEARCH_NAME = "Codex native web research"


class CollectionError(RuntimeError):
    """A safe collection routing or recording failure."""


class CollectionCapabilityUnavailable(CollectionError):
    """The request cannot be collected with any allowed available route."""


@dataclass(frozen=True)
class CollectionAttemptResult:
    status: Literal["accepted", "repair_required", "failed", "already_valid"]
    attempt: int
    report: ValidationReport

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "status": self.status,
            **self.report.to_dict(concise=True),
        }


@dataclass(frozen=True)
class CollectionRunContext:
    workspace: RunWorkspace
    manager: LeaseManager
    run_id: str
    allowed_input_roots: tuple[Path, ...]


def open_collection_run(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
) -> CollectionRunContext:
    """Resolve one active run and its profile-derived human summary context."""
    try:
        resolved_run = resolve_within_roots(
            run_directory,
            [settings.runtime_root],
            must_exist=True,
        )
        state = load_run_state(resolved_run / "state.json")
        profile_reference = state.artifacts.get("profile")
        if profile_reference is None or profile_reference.artifact_type != "profile":
            raise CollectionError("active state has no profile reference")
        profile = load_profile(
            Path(profile_reference.path),
            allowed_roots=[repo_root / "examples" / "profiles", *settings.input_roots],
        )
    except (LifecycleError, ProfileError, SafetyError) as error:
        raise CollectionError("run directory, state, or profile is invalid") from error
    episode_date = state.episode_date
    if episode_date is None:
        raise CollectionError("active run state has no episode date")
    title = profile.identity.title_template.replace("{date}", episode_date.isoformat())
    workspace = RunWorkspace(resolved_run, title, state.episode_key)
    try:
        manager = LeaseManager(
            settings.runtime_root,
            maximum_age=timedelta(seconds=settings.maximum_run_age_seconds),
        )
    except LeaseError as error:
        raise CollectionError("episode lease configuration is unavailable") from error
    return CollectionRunContext(
        workspace=workspace,
        manager=manager,
        run_id=state.run_id,
        allowed_input_roots=tuple(settings.input_roots),
    )


def select_collection_method(
    request: CollectionRequest,
    available_capabilities: Mapping[str, str | None],
    *,
    preferred_capability: str | None = None,
    failed_capabilities: Sequence[str] = (),
) -> CollectionMethod:
    """Choose from capabilities Codex already judged suitable, or use native fallback."""
    failed = set(failed_capabilities)
    missing_required = sorted(
        capability
        for capability in request.required_capabilities
        if capability not in available_capabilities or capability in failed
    )
    if missing_required:
        names = ", ".join(missing_required[:5])
        if len(missing_required) > 5:
            names += f" (+{len(missing_required) - 5} more)"
        raise CollectionCapabilityUnavailable(
            f"required collection capability unavailable: {names}; install or configure it "
            "before retrying this profile"
        )
    if preferred_capability is not None:
        if preferred_capability in failed:
            preferred_capability = None
        elif preferred_capability not in available_capabilities:
            raise CollectionError("preferred collection capability was not reported available")

    ordered = [
        preferred_capability,
        *request.required_capabilities,
        *request.suggested_capabilities,
    ]
    for capability in dict.fromkeys(item for item in ordered if item is not None):
        if capability in available_capabilities and capability not in failed:
            try:
                return CollectionMethod(
                    type="specialized_capability",
                    name=capability,
                    version=available_capabilities[capability],
                )
            except ValidationError as error:
                raise CollectionError("available capability metadata is invalid") from error

    if request.allow_native_research_fallback and "public_web" in request.source_types:
        return CollectionMethod(type="native_research", name=NATIVE_RESEARCH_NAME, version=None)
    raise CollectionCapabilityUnavailable(
        "no suitable collection capability is available and native public-web fallback is not "
        "allowed; install or configure a required capability"
    )


def record_collection_attempt(
    workspace: RunWorkspace,
    manager: LeaseManager,
    run_id: str,
    *,
    candidate_path: Path,
    allowed_input_roots: Sequence[Path] = (),
    now: datetime | None = None,
) -> CollectionAttemptResult:
    """Normalize, validate, persist, and record one of at most two dossier attempts."""
    state = load_run_state(workspace.state_path)
    if state.run_id != run_id:
        raise CollectionError("collection attempt run ID does not match active state")
    if state.collection_method is None:
        raise CollectionError("select and record a collection method before writing a dossier")
    request = load_collection_request(workspace, state.artifacts.get("collection_request"))
    if state.collection_validation and state.collection_validation.status == "valid":
        result = _load_valid_resume(
            workspace,
            state.collection_validation,
            request,
            allowed_input_roots,
        )
        refresh_run_summary(workspace, manager, run_id)
        return result

    previous = state.collection_validation
    if previous is not None and not previous.repair_allowed:
        raise CollectionError("collection validation repair limit is exhausted")
    attempt = 1 if previous is None else previous.attempt + 1
    try:
        candidate_path = resolve_within_roots(
            candidate_path,
            [workspace.run_directory],
            must_exist=False,
        )
        expected_path = resolve_within_roots(
            Path(request.output_path),
            [workspace.run_directory],
            must_exist=False,
        )
    except SafetyError as error:
        raise CollectionError("evidence dossier path is outside the run workspace") from error
    if candidate_path != expected_path:
        raise CollectionError("evidence dossier path does not match the collection request")
    candidate = _load_candidate(candidate_path)
    if isinstance(candidate, dict):
        mapping = cast(dict[str, object], candidate)
        candidate = _normalize_dossier(mapping, state.collection_method, request, state.artifacts)
        artifact, report = validate_artifact_data(
            "evidence",
            candidate,
            allowed_input_roots=allowed_input_roots,
        )
    else:
        artifact, report = load_artifact_file(
            "evidence",
            candidate_path,
            allowed_input_roots=allowed_input_roots,
        )

    if isinstance(artifact, EvidenceDossier):
        request_errors, request_warnings = validate_dossier_against_request(artifact, request)
        errors = tuple(sorted((*report.errors, *request_errors)))
        warnings = tuple(sorted((*report.warnings, *request_warnings)))
        report = ValidationReport("evidence", not errors, errors, warnings)

    validated_at = _aware_utc(now or datetime.now(UTC))
    repair_allowed = not report.valid and attempt == 1

    if report.valid:
        if not isinstance(artifact, EvidenceDossier):  # pragma: no cover - validator narrows it
            raise CollectionError("valid collection output is not an evidence dossier")
        record_collection_validation(
            workspace,
            manager,
            run_id,
            attempt=attempt,
            method=state.collection_method,
            report=report,
            now=validated_at,
            dossier=artifact,
            allowed_input_roots=allowed_input_roots,
        )
        return CollectionAttemptResult("accepted", attempt, report)

    record_collection_validation(
        workspace,
        manager,
        run_id,
        attempt=attempt,
        method=state.collection_method,
        report=report,
        now=validated_at,
    )
    status: Literal["repair_required", "failed"] = "repair_required" if repair_allowed else "failed"
    return CollectionAttemptResult(status, attempt, report)


def _normalize_dossier(
    data: dict[str, object],
    method: CollectionMethod,
    request: CollectionRequest,
    artifacts: Mapping[str, ArtifactReference],
) -> dict[str, object]:
    request_reference = artifacts.get("collection_request")
    if request_reference is None:
        raise CollectionError("active state has no collection request reference")
    normalized = copy.deepcopy(data)
    normalized.update(
        {
            "contract_version": request.evidence_contract_version,
            "prompt_version": COLLECTION_PROMPT_VERSION,
            "collection_request": request_reference.model_dump(mode="json"),
            "collection_method": method.model_dump(mode="json"),
            "limits": {
                "maximum_candidates": request.targets.maximum_candidates,
                "maximum_sources": request.targets.maximum_sources,
                "warning_estimated_tokens": request.targets.warning_estimated_tokens,
                "maximum_estimated_tokens": request.targets.maximum_estimated_tokens,
            },
        }
    )
    return normalized


def _load_candidate(path: Path) -> object:
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def load_collection_request(
    workspace: RunWorkspace,
    reference: ArtifactReference | None,
) -> CollectionRequest:
    if reference is None or reference.artifact_type != "collection-request":
        raise CollectionError("active state has no valid collection request reference")
    try:
        path = resolve_within_roots(
            workspace.run_directory / reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        if sha256_file(path) != reference.sha256:
            raise CollectionError("collection request file no longer matches active state")
        request, report = load_artifact_file(
            "collection-request",
            path,
            allowed_output_roots=[workspace.run_directory],
        )
    except (SafetyError, StorageError) as error:
        raise CollectionError("collection request file is missing or unsafe") from error
    if not report.valid or not isinstance(request, CollectionRequest):
        raise CollectionError("collection request file is invalid")
    return request


def _load_valid_resume(
    workspace: RunWorkspace,
    outcome: CollectionValidationState,
    request: CollectionRequest,
    allowed_input_roots: Sequence[Path],
) -> CollectionAttemptResult:
    state = load_run_state(workspace.state_path)
    evidence = state.artifacts.get("evidence_dossier")
    if evidence is None:
        raise CollectionError("valid collection state has no evidence dossier")
    try:
        evidence_path = resolve_within_roots(
            workspace.run_directory / evidence.path,
            [workspace.run_directory],
            must_exist=True,
        )
        report_path = resolve_within_roots(
            workspace.run_directory / outcome.report.path,
            [workspace.run_directory],
            must_exist=True,
        )
        if sha256_file(evidence_path) != evidence.sha256:
            raise CollectionError("recorded evidence dossier hash no longer matches its file")
        if sha256_file(report_path) != outcome.report.sha256:
            raise CollectionError("recorded collection validation hash no longer matches its file")
        artifact, report = load_artifact_file(
            "evidence",
            evidence_path,
            allowed_input_roots=allowed_input_roots,
        )
    except (SafetyError, StorageError) as error:
        raise CollectionError("recorded collection artifact is missing or unsafe") from error
    if isinstance(artifact, EvidenceDossier):
        request_errors, request_warnings = validate_dossier_against_request(artifact, request)
        errors = tuple(sorted((*report.errors, *request_errors)))
        warnings = tuple(sorted((*report.warnings, *request_warnings)))
        report = ValidationReport("evidence", not errors, errors, warnings)
    if not report.valid:
        raise CollectionError("recorded evidence dossier is no longer valid")
    return CollectionAttemptResult("already_valid", outcome.attempt, report)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CollectionError("collection timestamps must be timezone-aware")
    return value.astimezone(UTC)
