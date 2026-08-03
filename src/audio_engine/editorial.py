"""Topic-generic editorial-plan normalization, validation, recording, and resume."""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from audio_engine.artifacts import EditorialPlan, EvidenceDossier, PlanValidationState, RunState
from audio_engine.collection import CollectionError, load_collection_request
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseError, LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    load_run_state,
    record_plan_validation,
    refresh_run_summary,
)
from audio_engine.profile import EpisodeProfile, ProfileError, load_profile
from audio_engine.safety import SafetyError, resolve_within_roots
from audio_engine.storage import StorageError, sha256_file
from audio_engine.validation import (
    ValidationReport,
    load_artifact_file,
    validate_artifact_data,
    validate_dossier_against_request,
    validate_plan_against_dossier,
    validate_plan_against_profile,
)

EDITORIAL_PROMPT_VERSION = "1.0.0"


class EditorialError(RuntimeError):
    """A safe editorial-plan recording or resume failure."""


@dataclass(frozen=True)
class EditorialAttemptResult:
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
class EditorialRunContext:
    workspace: RunWorkspace
    manager: LeaseManager
    run_id: str
    profile: EpisodeProfile
    allowed_input_roots: tuple[Path, ...]
    allowed_profile_roots: tuple[Path, ...]


def open_editorial_run(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
) -> EditorialRunContext:
    """Resolve an active run and verify its profile reference before editorial work."""
    profile_roots = (repo_root / "examples" / "profiles", *settings.input_roots)
    try:
        resolved_run = resolve_within_roots(
            run_directory,
            [settings.runtime_root],
            must_exist=True,
        )
        state = load_run_state(resolved_run / "state.json")
        profile_reference = state.artifacts.get("profile")
        if profile_reference is None or profile_reference.artifact_type != "profile":
            raise EditorialError("active state has no profile reference")
        profile_path = resolve_within_roots(
            Path(profile_reference.path),
            profile_roots,
            must_exist=True,
        )
        if sha256_file(profile_path) != profile_reference.sha256:
            raise EditorialError("profile file no longer matches active state")
        profile = load_profile(profile_path, allowed_roots=profile_roots)
    except (LifecycleError, ProfileError, SafetyError, StorageError) as error:
        raise EditorialError("run directory, state, or profile is invalid") from error
    if profile.id != state.profile_id or profile.version != state.profile_version:
        raise EditorialError("profile identity no longer matches active state")
    if state.episode_date is None:
        raise EditorialError("active run state has no episode date")
    title = profile.identity.title_template.replace("{date}", state.episode_date.isoformat())
    workspace = RunWorkspace(resolved_run, title, state.episode_key)
    try:
        manager = LeaseManager(
            settings.runtime_root,
            maximum_age=timedelta(seconds=settings.maximum_run_age_seconds),
        )
    except LeaseError as error:
        raise EditorialError("episode lease configuration is unavailable") from error
    return EditorialRunContext(
        workspace=workspace,
        manager=manager,
        run_id=state.run_id,
        profile=profile,
        allowed_input_roots=tuple(settings.input_roots),
        allowed_profile_roots=tuple(profile_roots),
    )


def record_editorial_attempt(
    workspace: RunWorkspace,
    manager: LeaseManager,
    run_id: str,
    *,
    profile: EpisodeProfile,
    candidate_path: Path,
    allowed_input_roots: Sequence[Path] = (),
    allowed_profile_roots: Sequence[Path] = (),
    now: datetime | None = None,
) -> EditorialAttemptResult:
    """Normalize, validate, persist, and record one of at most two plan attempts."""
    state, dossier = _load_editorial_inputs(
        workspace,
        run_id,
        profile,
        allowed_input_roots=allowed_input_roots,
        allowed_profile_roots=allowed_profile_roots,
    )
    if state.plan_validation and state.plan_validation.status == "valid":
        result = _load_valid_resume(
            workspace,
            state,
            state.plan_validation,
            dossier,
            profile,
        )
        refresh_run_summary(workspace, manager, run_id)
        return result
    if state.current_stage != "editorial":
        raise EditorialError("editorial plan can only be recorded during editorial")

    previous = state.plan_validation
    if previous is not None and not previous.repair_allowed:
        raise EditorialError("plan validation repair limit is exhausted")
    attempt = 1 if previous is None else previous.attempt + 1
    validated_at = _aware_utc(now or datetime.now(UTC))
    try:
        candidate_path = resolve_within_roots(
            candidate_path,
            [workspace.run_directory],
            must_exist=False,
        )
        expected_path = resolve_within_roots(
            workspace.run_directory / "editorial-plan.json",
            [workspace.run_directory],
            must_exist=False,
        )
    except SafetyError as error:
        raise EditorialError("editorial plan path is outside the run workspace") from error
    if candidate_path != expected_path:
        raise EditorialError("editorial plan path does not match the run workspace")

    candidate = _load_candidate(candidate_path)
    if isinstance(candidate, dict):
        candidate = _normalize_plan(cast(dict[str, object], candidate), state, validated_at)
    artifact, report = validate_artifact_data("plan", candidate)
    if isinstance(artifact, EditorialPlan):
        dossier_errors = validate_plan_against_dossier(artifact, dossier)
        profile_errors, profile_warnings = validate_plan_against_profile(
            artifact,
            dossier,
            profile,
        )
        errors = tuple(sorted((*report.errors, *dossier_errors, *profile_errors)))
        warnings = tuple(sorted((*report.warnings, *profile_warnings)))
        report = ValidationReport("plan", not errors, errors, warnings)

    repair_allowed = not report.valid and attempt == 1
    if report.valid:
        if not isinstance(artifact, EditorialPlan):  # pragma: no cover - validator narrows it
            raise EditorialError("valid editorial output is not an editorial plan")
        record_plan_validation(
            workspace,
            manager,
            run_id,
            attempt=attempt,
            prompt_version=EDITORIAL_PROMPT_VERSION,
            report=report,
            now=validated_at,
            plan=artifact,
            allowed_profile_roots=allowed_profile_roots,
        )
        return EditorialAttemptResult("accepted", attempt, report)

    record_plan_validation(
        workspace,
        manager,
        run_id,
        attempt=attempt,
        prompt_version=EDITORIAL_PROMPT_VERSION,
        report=report,
        now=validated_at,
    )
    status: Literal["repair_required", "failed"] = "repair_required" if repair_allowed else "failed"
    return EditorialAttemptResult(status, attempt, report)


def _load_editorial_inputs(
    workspace: RunWorkspace,
    run_id: str,
    profile: EpisodeProfile,
    *,
    allowed_input_roots: Sequence[Path],
    allowed_profile_roots: Sequence[Path],
) -> tuple[RunState, EvidenceDossier]:
    state = load_run_state(workspace.state_path)
    if state.run_id != run_id:
        raise EditorialError("editorial attempt run ID does not match active state")
    if state.collection_validation is None or state.collection_validation.status != "valid":
        raise EditorialError("editorial work requires a valid collection outcome")
    profile_reference = state.artifacts.get("profile")
    evidence_reference = state.artifacts.get("evidence_dossier")
    validation_reference = state.artifacts.get("evidence_validation")
    if (
        profile_reference is None
        or profile_reference.artifact_type != "profile"
        or evidence_reference is None
        or evidence_reference.artifact_type != "evidence"
        or validation_reference is None
        or validation_reference != state.collection_validation.report
    ):
        raise EditorialError("editorial input references are incomplete")
    try:
        profile_path = resolve_within_roots(
            Path(profile_reference.path),
            allowed_profile_roots,
            must_exist=True,
        )
        evidence_path = resolve_within_roots(
            workspace.run_directory / evidence_reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        validation_path = resolve_within_roots(
            workspace.run_directory / validation_reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        if sha256_file(profile_path) != profile_reference.sha256:
            raise EditorialError("recorded profile hash no longer matches its file")
        if sha256_file(evidence_path) != evidence_reference.sha256:
            raise EditorialError("recorded evidence dossier hash no longer matches its file")
        if sha256_file(validation_path) != validation_reference.sha256:
            raise EditorialError("recorded collection validation hash no longer matches its file")
        artifact, report = load_artifact_file(
            "evidence",
            evidence_path,
            allowed_input_roots=allowed_input_roots,
        )
    except (SafetyError, StorageError) as error:
        raise EditorialError("recorded editorial input is missing or unsafe") from error
    if not isinstance(artifact, EvidenceDossier):
        raise EditorialError("recorded evidence dossier is invalid")
    try:
        request = load_collection_request(workspace, state.artifacts.get("collection_request"))
    except CollectionError as error:
        raise EditorialError("recorded collection request is invalid") from error
    request_errors, _ = validate_dossier_against_request(artifact, request)
    if not report.valid or request_errors:
        raise EditorialError("recorded evidence dossier is no longer valid")
    if profile.id != state.profile_id or profile.version != state.profile_version:
        raise EditorialError("profile identity no longer matches active state")
    return state, artifact


def _normalize_plan(data: dict[str, object], state: RunState, now: datetime) -> dict[str, object]:
    profile_reference = state.artifacts.get("profile")
    evidence_reference = state.artifacts.get("evidence_dossier")
    if profile_reference is None or evidence_reference is None or state.episode_date is None:
        raise EditorialError("active state has incomplete editorial provenance")
    normalized = copy.deepcopy(data)
    normalized.update(
        {
            "contract_version": "1.0",
            "prompt_version": EDITORIAL_PROMPT_VERSION,
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "run_id": state.run_id,
            "profile_id": state.profile_id,
            "episode_date": state.episode_date.isoformat(),
            "profile": profile_reference.model_dump(mode="json"),
            "evidence_dossier": evidence_reference.model_dump(mode="json"),
        }
    )
    return normalized


def _load_candidate(path: Path) -> object:
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _load_valid_resume(
    workspace: RunWorkspace,
    state: RunState,
    outcome: PlanValidationState,
    dossier: EvidenceDossier,
    profile: EpisodeProfile,
) -> EditorialAttemptResult:
    plan_reference = state.artifacts.get("editorial_plan")
    if plan_reference is None or plan_reference.artifact_type != "plan":
        raise EditorialError("valid plan state has no editorial plan")
    try:
        plan_path = resolve_within_roots(
            workspace.run_directory / plan_reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        report_path = resolve_within_roots(
            workspace.run_directory / outcome.report.path,
            [workspace.run_directory],
            must_exist=True,
        )
        if sha256_file(plan_path) != plan_reference.sha256:
            raise EditorialError("recorded editorial plan hash no longer matches its file")
        if sha256_file(report_path) != outcome.report.sha256:
            raise EditorialError("recorded plan validation hash no longer matches its file")
        artifact, report = load_artifact_file("plan", plan_path)
    except (SafetyError, StorageError) as error:
        raise EditorialError("recorded editorial artifact is missing or unsafe") from error
    if not isinstance(artifact, EditorialPlan):
        raise EditorialError("recorded editorial plan is invalid")
    if (
        artifact.prompt_version != EDITORIAL_PROMPT_VERSION
        or artifact.run_id != state.run_id
        or artifact.profile_id != state.profile_id
        or artifact.episode_date != state.episode_date
        or artifact.profile != state.artifacts.get("profile")
        or artifact.evidence_dossier != state.artifacts.get("evidence_dossier")
    ):
        raise EditorialError("recorded editorial plan provenance no longer matches active state")
    dossier_errors = validate_plan_against_dossier(artifact, dossier)
    profile_errors, profile_warnings = validate_plan_against_profile(artifact, dossier, profile)
    errors = tuple(sorted((*report.errors, *dossier_errors, *profile_errors)))
    warnings = tuple(sorted((*report.warnings, *profile_warnings)))
    report = ValidationReport("plan", not errors, errors, warnings)
    if not report.valid:
        raise EditorialError("recorded editorial plan is no longer valid")
    return EditorialAttemptResult("already_valid", outcome.attempt, report)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EditorialError("editorial timestamps must be timezone-aware")
    return value.astimezone(UTC)
