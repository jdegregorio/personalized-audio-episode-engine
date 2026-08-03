"""Grounded script normalization, transcript projection, validation, and resume."""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from audio_engine.artifacts import (
    ArtifactReference,
    EditorialPlan,
    EpisodeScript,
    EvidenceDossier,
    RunState,
    ScriptValidationState,
)
from audio_engine.collection import CollectionError, load_collection_request
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseError, LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    load_run_state,
    record_script_validation,
    refresh_run_summary,
)
from audio_engine.profile import EpisodeProfile, ProfileError, load_profile
from audio_engine.safety import SafetyError, resolve_within_roots
from audio_engine.storage import StorageError, sha256_bytes, sha256_file
from audio_engine.validation import (
    ValidationReport,
    load_artifact_file,
    render_transcript,
    validate_artifact_data,
    validate_dossier_against_request,
    validate_plan_against_dossier,
    validate_plan_against_profile,
    validate_script_against_plan_and_dossier,
    validate_script_against_profile,
    validate_transcript_projection,
)

SCRIPT_PROMPT_VERSION = "1.0.0"


class ScriptwritingError(RuntimeError):
    """A safe script recording or resume failure."""


@dataclass(frozen=True)
class ScriptAttemptResult:
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
class ScriptRunContext:
    workspace: RunWorkspace
    manager: LeaseManager
    run_id: str
    profile: EpisodeProfile
    allowed_input_roots: tuple[Path, ...]
    allowed_profile_roots: tuple[Path, ...]


def open_script_run(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
) -> ScriptRunContext:
    """Resolve an active run and verify its authoritative profile."""
    profile_roots = (repo_root / "examples" / "profiles", *settings.input_roots)
    try:
        resolved_run = resolve_within_roots(run_directory, [settings.runtime_root], must_exist=True)
        state = load_run_state(resolved_run / "state.json")
        profile_reference = state.artifacts.get("profile")
        if profile_reference is None or profile_reference.artifact_type != "profile":
            raise ScriptwritingError("active state has no profile reference")
        profile_path = resolve_within_roots(
            Path(profile_reference.path), profile_roots, must_exist=True
        )
        if sha256_file(profile_path) != profile_reference.sha256:
            raise ScriptwritingError("profile file no longer matches active state")
        profile = load_profile(profile_path, allowed_roots=profile_roots)
    except (LifecycleError, ProfileError, SafetyError, StorageError) as error:
        raise ScriptwritingError("run directory, state, or profile is invalid") from error
    if profile.id != state.profile_id or profile.version != state.profile_version:
        raise ScriptwritingError("profile identity no longer matches active state")
    if state.episode_date is None:
        raise ScriptwritingError("active run state has no episode date")
    title = profile.identity.title_template.replace("{date}", state.episode_date.isoformat())
    try:
        manager = LeaseManager(
            settings.runtime_root,
            maximum_age=timedelta(seconds=settings.maximum_run_age_seconds),
        )
    except LeaseError as error:
        raise ScriptwritingError("episode lease configuration is unavailable") from error
    return ScriptRunContext(
        workspace=RunWorkspace(resolved_run, title, state.episode_key),
        manager=manager,
        run_id=state.run_id,
        profile=profile,
        allowed_input_roots=tuple(settings.input_roots),
        allowed_profile_roots=tuple(profile_roots),
    )


def record_script_attempt(
    workspace: RunWorkspace,
    manager: LeaseManager,
    run_id: str,
    *,
    profile: EpisodeProfile,
    candidate_path: Path,
    allowed_input_roots: Sequence[Path] = (),
    allowed_profile_roots: Sequence[Path] = (),
    now: datetime | None = None,
) -> ScriptAttemptResult:
    """Validate and durably record one of at most two script attempts."""
    state, dossier, plan = _load_script_inputs(
        workspace,
        run_id,
        profile,
        allowed_input_roots=allowed_input_roots,
        allowed_profile_roots=allowed_profile_roots,
    )
    if state.script_validation and state.script_validation.status == "valid":
        result = _load_valid_resume(
            workspace, state, state.script_validation, dossier, plan, profile
        )
        refresh_run_summary(workspace, manager, run_id)
        return result
    if state.current_stage != "script":
        raise ScriptwritingError("episode script can only be recorded during script")
    previous = state.script_validation
    if previous is not None and not previous.repair_allowed:
        raise ScriptwritingError("script validation repair limit is exhausted")
    attempt = 1 if previous is None else previous.attempt + 1
    validated_at = _aware_utc(now or datetime.now(UTC))

    try:
        candidate_path = resolve_within_roots(
            candidate_path, [workspace.run_directory], must_exist=False
        )
        expected_path = resolve_within_roots(
            workspace.run_directory / "episode-script.json",
            [workspace.run_directory],
            must_exist=False,
        )
    except SafetyError as error:
        raise ScriptwritingError("episode script path is outside the run workspace") from error
    if candidate_path != expected_path:
        raise ScriptwritingError("episode script path does not match the run workspace")

    candidate = _load_candidate(candidate_path)
    transcript: str | None = None
    artifact: EpisodeScript | None = None
    if isinstance(candidate, dict):
        normalized = _normalize_script(cast(dict[str, object], candidate), state, validated_at)
        initial, report = validate_artifact_data("script", normalized)
        if isinstance(initial, EpisodeScript):
            transcript = render_transcript(initial)
            normalized["transcript"] = _transcript_reference(transcript).model_dump(mode="json")
            validated, report = validate_artifact_data("script", normalized)
            artifact = validated if isinstance(validated, EpisodeScript) else None
    else:
        _, report = validate_artifact_data("script", candidate)

    if artifact is not None and transcript is not None:
        lineage_errors = validate_script_against_plan_and_dossier(artifact, plan, dossier)
        profile_errors, profile_warnings = validate_script_against_profile(artifact, plan, profile)
        transcript_errors = validate_transcript_projection(artifact, transcript)
        errors = tuple(
            sorted((*report.errors, *lineage_errors, *profile_errors, *transcript_errors))
        )
        report = ValidationReport("script", not errors, errors, tuple(sorted(profile_warnings)))

    repair_allowed = not report.valid and attempt == 1
    if report.valid:
        if artifact is None or transcript is None:  # pragma: no cover - validator narrows it
            raise ScriptwritingError("valid script output is incomplete")
        record_script_validation(
            workspace,
            manager,
            run_id,
            attempt=attempt,
            prompt_version=SCRIPT_PROMPT_VERSION,
            report=report,
            now=validated_at,
            script=artifact,
            transcript=transcript,
            allowed_input_roots=allowed_profile_roots,
        )
        return ScriptAttemptResult("accepted", attempt, report)

    record_script_validation(
        workspace,
        manager,
        run_id,
        attempt=attempt,
        prompt_version=SCRIPT_PROMPT_VERSION,
        report=report,
        now=validated_at,
    )
    status: Literal["repair_required", "failed"] = "repair_required" if repair_allowed else "failed"
    return ScriptAttemptResult(status, attempt, report)


def _load_script_inputs(
    workspace: RunWorkspace,
    run_id: str,
    profile: EpisodeProfile,
    *,
    allowed_input_roots: Sequence[Path],
    allowed_profile_roots: Sequence[Path],
) -> tuple[RunState, EvidenceDossier, EditorialPlan]:
    state = load_run_state(workspace.state_path)
    if state.run_id != run_id:
        raise ScriptwritingError("script attempt run ID does not match active state")
    if (
        state.collection_validation is None
        or state.collection_validation.status != "valid"
        or state.plan_validation is None
        or state.plan_validation.status != "valid"
    ):
        raise ScriptwritingError("script work requires a valid editorial plan")
    profile_reference = state.artifacts.get("profile")
    evidence_reference = state.artifacts.get("evidence_dossier")
    evidence_validation = state.artifacts.get("evidence_validation")
    plan_reference = state.artifacts.get("editorial_plan")
    plan_validation = state.artifacts.get("plan_validation")
    if (
        profile_reference is None
        or profile_reference.artifact_type != "profile"
        or evidence_reference is None
        or evidence_reference.artifact_type != "evidence"
        or evidence_validation is None
        or evidence_validation != state.collection_validation.report
        or plan_reference is None
        or plan_reference.artifact_type != "plan"
        or plan_validation is None
        or plan_validation != state.plan_validation.report
    ):
        raise ScriptwritingError("script input references are incomplete")
    try:
        profile_path = resolve_within_roots(
            Path(profile_reference.path), allowed_profile_roots, must_exist=True
        )
        evidence_path = resolve_within_roots(
            workspace.run_directory / evidence_reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        evidence_validation_path = resolve_within_roots(
            workspace.run_directory / evidence_validation.path,
            [workspace.run_directory],
            must_exist=True,
        )
        plan_path = resolve_within_roots(
            workspace.run_directory / plan_reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        plan_validation_path = resolve_within_roots(
            workspace.run_directory / plan_validation.path,
            [workspace.run_directory],
            must_exist=True,
        )
        expected_hashes = (
            (profile_path, profile_reference.sha256),
            (evidence_path, evidence_reference.sha256),
            (evidence_validation_path, evidence_validation.sha256),
            (plan_path, plan_reference.sha256),
            (plan_validation_path, plan_validation.sha256),
        )
        if any(sha256_file(path) != expected for path, expected in expected_hashes):
            raise ScriptwritingError("recorded script input hash no longer matches its file")
        dossier_artifact, dossier_report = load_artifact_file(
            "evidence", evidence_path, allowed_input_roots=allowed_input_roots
        )
        plan_artifact, plan_report = load_artifact_file("plan", plan_path)
    except (SafetyError, StorageError) as error:
        raise ScriptwritingError("recorded script input is missing or unsafe") from error
    if not isinstance(dossier_artifact, EvidenceDossier) or not dossier_report.valid:
        raise ScriptwritingError("recorded evidence dossier is invalid")
    if not isinstance(plan_artifact, EditorialPlan) or not plan_report.valid:
        raise ScriptwritingError("recorded editorial plan is invalid")
    try:
        request = load_collection_request(workspace, state.artifacts.get("collection_request"))
    except CollectionError as error:
        raise ScriptwritingError("recorded collection request is invalid") from error
    request_errors, _ = validate_dossier_against_request(dossier_artifact, request)
    plan_lineage = validate_plan_against_dossier(plan_artifact, dossier_artifact)
    plan_profile_errors, _ = validate_plan_against_profile(plan_artifact, dossier_artifact, profile)
    if request_errors or plan_lineage or plan_profile_errors:
        raise ScriptwritingError("recorded script inputs are no longer valid")
    if profile.id != state.profile_id or profile.version != state.profile_version:
        raise ScriptwritingError("profile identity no longer matches active state")
    return state, dossier_artifact, plan_artifact


def _normalize_script(data: dict[str, object], state: RunState, now: datetime) -> dict[str, object]:
    profile_reference = state.artifacts.get("profile")
    evidence_reference = state.artifacts.get("evidence_dossier")
    plan_reference = state.artifacts.get("editorial_plan")
    if (
        profile_reference is None
        or evidence_reference is None
        or plan_reference is None
        or state.episode_date is None
    ):
        raise ScriptwritingError("active state has incomplete script provenance")
    normalized = copy.deepcopy(data)
    normalized.update(
        {
            "contract_version": "1.0",
            "prompt_version": SCRIPT_PROMPT_VERSION,
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "run_id": state.run_id,
            "profile_id": state.profile_id,
            "episode_date": state.episode_date.isoformat(),
            "profile": profile_reference.model_dump(mode="json"),
            "evidence_dossier": evidence_reference.model_dump(mode="json"),
            "editorial_plan": plan_reference.model_dump(mode="json"),
            "transcript": _transcript_reference("").model_dump(mode="json"),
        }
    )
    return normalized


def _transcript_reference(transcript: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_type="transcript",
        path="transcript.txt",
        sha256=sha256_bytes(transcript.encode("utf-8")),
    )


def _load_candidate(path: Path) -> object:
    try:
        return cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _load_valid_resume(
    workspace: RunWorkspace,
    state: RunState,
    outcome: ScriptValidationState,
    dossier: EvidenceDossier,
    plan: EditorialPlan,
    profile: EpisodeProfile,
) -> ScriptAttemptResult:
    script_reference = state.artifacts.get("episode_script")
    transcript_reference = state.artifacts.get("transcript")
    validation_reference = state.artifacts.get("script_validation")
    if script_reference is None or script_reference.artifact_type != "script":
        raise ScriptwritingError("valid script state has no episode script")
    if transcript_reference is None or transcript_reference.artifact_type != "transcript":
        raise ScriptwritingError("valid script state has no transcript")
    if validation_reference is None or validation_reference != outcome.report:
        raise ScriptwritingError("valid script state has no matching validation report")
    try:
        script_path = resolve_within_roots(
            workspace.run_directory / script_reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        transcript_path = resolve_within_roots(
            workspace.run_directory / transcript_reference.path,
            [workspace.run_directory],
            must_exist=True,
        )
        report_path = resolve_within_roots(
            workspace.run_directory / outcome.report.path,
            [workspace.run_directory],
            must_exist=True,
        )
        for path, expected in (
            (script_path, script_reference.sha256),
            (transcript_path, transcript_reference.sha256),
            (report_path, outcome.report.sha256),
        ):
            if sha256_file(path) != expected:
                raise ScriptwritingError("recorded script output hash no longer matches its file")
        artifact, report = load_artifact_file("script", script_path)
        transcript = transcript_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, SafetyError, StorageError) as error:
        raise ScriptwritingError("recorded script output is missing or unsafe") from error
    if not isinstance(artifact, EpisodeScript):
        raise ScriptwritingError("recorded episode script is invalid")
    if (
        artifact.prompt_version != SCRIPT_PROMPT_VERSION
        or artifact.run_id != state.run_id
        or artifact.profile_id != state.profile_id
        or artifact.episode_date != state.episode_date
        or artifact.profile != state.artifacts.get("profile")
        or artifact.evidence_dossier != state.artifacts.get("evidence_dossier")
        or artifact.editorial_plan != state.artifacts.get("editorial_plan")
        or artifact.transcript != transcript_reference
    ):
        raise ScriptwritingError("recorded episode script provenance no longer matches state")
    lineage_errors = validate_script_against_plan_and_dossier(artifact, plan, dossier)
    profile_errors, warnings = validate_script_against_profile(artifact, plan, profile)
    transcript_errors = validate_transcript_projection(artifact, transcript)
    errors = tuple(sorted((*report.errors, *lineage_errors, *profile_errors, *transcript_errors)))
    report = ValidationReport("script", not errors, errors, tuple(sorted(warnings)))
    if not report.valid:
        raise ScriptwritingError("recorded episode script is no longer valid")
    return ScriptAttemptResult("already_valid", outcome.attempt, report)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ScriptwritingError("script timestamps must be timezone-aware")
    return value.astimezone(UTC)
