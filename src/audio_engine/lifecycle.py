"""Run initialization, durable state mutation, and dependency invalidation."""

from __future__ import annotations

import secrets
import subprocess
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from audio_engine import __version__
from audio_engine.artifacts import (
    ArtifactReference,
    CollectionAudience,
    CollectionEditorialPriorities,
    CollectionRequest,
    CollectionTargets,
    FinalAudioValidation,
    PublicationState,
    RequestScope,
    RequestTimeWindow,
    RunFailure,
    RunStage,
    RunState,
    SourcePolicy,
)
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseError, LeaseManager
from audio_engine.profile import EpisodeProfile, ProfileError, load_profile
from audio_engine.safety import SafetyError, redact_text, resolve_episode_date, resolve_within_roots
from audio_engine.storage import (
    StorageError,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    json_bytes,
    sha256_bytes,
    sha256_file,
)
from audio_engine.validation import load_artifact_file, validate_artifact_data

SKILL_VERSION = "0.1.0"


class LifecycleError(RuntimeError):
    """A safe, operator-facing run lifecycle failure."""


@dataclass(frozen=True)
class RunWorkspace:
    run_directory: Path
    episode_title: str
    episode_key: str

    @property
    def state_path(self) -> Path:
        return self.run_directory / "state.json"

    @property
    def summary_path(self) -> Path:
        return self.run_directory / "summary.md"


@dataclass(frozen=True)
class InitializationResult:
    result: Literal["initialized", "no_op"]
    episode_key: str
    run_id: str | None
    run_directory: Path | None
    recovered_stale_lease: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "episode_key": self.episode_key,
            "recovered_stale_lease": self.recovered_stale_lease,
            "result": self.result,
            "run_directory": str(self.run_directory) if self.run_directory else None,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class _ArtifactStageRule:
    artifact_type: str
    filename: str
    completed_stage: RunStage
    next_stage: RunStage
    downstream_keys: frozenset[str]


_ARTIFACT_DEPENDENCY_ORDER = (
    "profile",
    "collection_request",
    "evidence_dossier",
    "evidence_validation",
    "editorial_plan",
    "plan_validation",
    "episode_script",
    "script_validation",
    "transcript",
    "tts_manifest",
    "final_audio",
    "show_notes",
    "published_episode",
)


def _downstream_of(artifact_key: str) -> frozenset[str]:
    index = _ARTIFACT_DEPENDENCY_ORDER.index(artifact_key)
    return frozenset(_ARTIFACT_DEPENDENCY_ORDER[index + 1 :])


_FINAL_OUTPUT_KEYS = frozenset({"final_audio", "published_episode"})
_ARTIFACT_RULES: dict[str, _ArtifactStageRule] = {
    "collection_request": _ArtifactStageRule(
        "collection-request",
        "collection-request.json",
        "initialized",
        "collection",
        _downstream_of("collection_request"),
    ),
    "evidence_dossier": _ArtifactStageRule(
        "evidence",
        "evidence-dossier.json",
        "collection",
        "editorial",
        _downstream_of("evidence_dossier"),
    ),
    "editorial_plan": _ArtifactStageRule(
        "plan",
        "editorial-plan.json",
        "editorial",
        "script",
        _downstream_of("editorial_plan"),
    ),
    "episode_script": _ArtifactStageRule(
        "script",
        "episode-script.json",
        "script",
        "tts",
        _downstream_of("episode_script"),
    ),
}
_PROFILE_DOWNSTREAM_KEYS = _downstream_of("profile")


def canonical_episode_key(profile_id: str, episode_date: date) -> str:
    """Return the one canonical key shared by leases and publication."""
    return f"{profile_id}:{episode_date.isoformat()}"


def generate_run_id(profile_id: str, episode_date: date, *, now: datetime) -> str:
    """Return a sortable, collision-resistant identifier for one owning execution."""
    instant = _aware_utc(now)
    timestamp = instant.strftime("%Y%m%dT%H%M%S%fZ")
    return f"{profile_id}_{episode_date.isoformat()}_{timestamp}_{secrets.token_hex(4)}"


def initialize_run(
    profile_path: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
    clock: Callable[[], datetime] | None = None,
    run_id_factory: Callable[[str, date, datetime], str] | None = None,
    codex_model: str | None = None,
) -> InitializationResult:
    """Acquire episode ownership and create the initial durable run artifacts."""
    current_time = clock or (lambda: datetime.now(UTC))
    now = _aware_utc(current_time())
    allowed_profile_roots = [repo_root / "examples" / "profiles", *settings.input_roots]
    try:
        profile = load_profile(profile_path, allowed_roots=allowed_profile_roots)
        resolved_profile_path = resolve_within_roots(
            profile_path,
            allowed_profile_roots,
            must_exist=True,
        )
        episode_date = resolve_episode_date(profile.audience.timezone, now=now)
    except (ProfileError, SafetyError, ValueError) as error:
        raise LifecycleError(str(error)) from None

    episode_key = canonical_episode_key(profile.id, episode_date)
    run_id = (
        run_id_factory(profile.id, episode_date, now)
        if run_id_factory is not None
        else generate_run_id(profile.id, episode_date, now=now)
    )
    try:
        manager = LeaseManager(
            settings.runtime_root,
            maximum_age=timedelta(seconds=settings.maximum_run_age_seconds),
            clock=current_time,
        )
        acquisition = manager.acquire(episode_key, run_id)
    except (LeaseError, ValidationError) as error:
        raise LifecycleError(str(error)) from None
    if not acquisition.acquired:
        return InitializationResult("no_op", episode_key, None, None)

    workspace: RunWorkspace | None = None
    state: RunState | None = None
    try:
        run_directory = _create_run_directory(
            settings.runtime_root,
            episode_date,
            profile.id,
            run_id,
        )
        title = profile.identity.title_template.replace("{date}", episode_date.isoformat())
        workspace = RunWorkspace(run_directory, title, episode_key)
        state = _initial_state(
            profile,
            resolved_profile_path,
            episode_key=episode_key,
            episode_date=episode_date,
            run_id=run_id,
            now=now,
            repo_root=repo_root,
            codex_model=codex_model,
        )
        _write_run_state(workspace, state)
        _write_summary(workspace, state)
        request = build_collection_request(
            profile,
            run_id=run_id,
            episode_date=episode_date,
            now=now,
            run_directory=run_directory,
        )
        state = persist_stage_artifact(
            workspace,
            manager,
            run_id,
            artifact_key="collection_request",
            data=request.model_dump(mode="json"),
        )
    except (LifecycleError, LeaseError, StorageError, OSError, ValidationError):
        terminal_persisted = False
        if workspace is not None and state is not None:
            try:
                failed_state = _failed_state(
                    state,
                    RunFailure(
                        stage="initialized",
                        code="initialization_failed",
                        message="Run initialization did not complete.",
                        recovery_guidance=(
                            "Inspect state and summary, correct local storage or input, then retry "
                            "after the lease is released or stale."
                        ),
                    ),
                    now,
                )
                _write_run_state(workspace, failed_state)
                _write_summary(workspace, failed_state)
                terminal_persisted = True
            except (LifecycleError, StorageError, OSError, ValidationError):
                terminal_persisted = False
        if terminal_persisted:
            with suppress(LeaseError):
                manager.release(episode_key, run_id)
        raise LifecycleError(
            "run initialization failed; inspect the run summary or recover the stale lease"
        ) from None

    return InitializationResult(
        "initialized",
        episode_key,
        run_id,
        workspace.run_directory,
        acquisition.recovered,
    )


def build_collection_request(
    profile: EpisodeProfile,
    *,
    run_id: str,
    episode_date: date,
    now: datetime,
    run_directory: Path,
) -> CollectionRequest:
    """Translate one validated profile into the topic-generic collection contract."""
    if profile.collection.evidence_contract_version != "1.0":
        raise LifecycleError("profile requires an unsupported evidence contract version")
    policy = dict(profile.editorial.policy)
    raw_publishers = policy.get("preferred_publishers", [])
    preferred_publishers = (
        [item for item in raw_publishers if isinstance(item, str)]
        if isinstance(raw_publishers, list)
        else []
    )
    prefer_primary = policy.get("prefer_primary", True)
    multiple_sources = policy.get("multiple_sources_for_consequential_claims", True)
    return CollectionRequest(
        contract_version="1.0",
        prompt_version=None,
        created_at=_aware_utc(now),
        run_id=run_id,
        profile_id=profile.id,
        episode_date=episode_date,
        timezone=profile.audience.timezone,
        topic=profile.episode.topic,
        scope=RequestScope(
            sections=[section.id for section in profile.episode.scope.sections],
            notes=(
                "Profile-defined section identifiers; descriptions remain authoritative in profile."
            ),
        ),
        audience=CollectionAudience(
            locale=profile.audience.locale,
            knowledge_level=profile.audience.knowledge_level,
            preferences=profile.audience.preferences,
        ),
        editorial_priorities=CollectionEditorialPriorities(
            exclusions=profile.episode.scope.exclude,
            policy=policy,
        ),
        time_window=RequestTimeWindow(hours=profile.collection.time_window.recency_hours),
        source_types=profile.collection.source_types,
        suggested_capabilities=profile.collection.suggested_capabilities,
        allow_native_research_fallback=profile.collection.allow_native_research_fallback,
        evidence_contract_version=profile.collection.evidence_contract_version,
        source_policy=SourcePolicy(
            prefer_primary=prefer_primary if isinstance(prefer_primary, bool) else True,
            preferred_publishers=preferred_publishers,
            multiple_sources_for_consequential_claims=(
                multiple_sources if isinstance(multiple_sources, bool) else True
            ),
            policy=policy,
        ),
        targets=CollectionTargets(
            by_section=profile.collection.target_candidates,
            maximum_candidates=profile.collection.maximum_candidates,
            maximum_sources=profile.collection.maximum_sources,
        ),
        output_path=str(run_directory / "evidence-dossier.json"),
    )


def persist_stage_artifact(
    workspace: RunWorkspace,
    manager: LeaseManager,
    run_id: str,
    *,
    artifact_key: str,
    data: object,
    allowed_input_roots: Sequence[Path] = (),
) -> RunState:
    """Write, validate, hash, and only then advance state under lease ownership."""
    rule = _ARTIFACT_RULES.get(artifact_key)
    if rule is None:
        raise LifecycleError("artifact key does not own a lifecycle stage")
    try:
        manager.refresh(workspace.episode_key, run_id)
    except LeaseError as error:
        raise LifecycleError(str(error)) from None
    state = load_run_state(workspace.state_path)
    if state.run_id != run_id or state.status != "running":
        raise LifecycleError("only the active run owner may mutate running state")
    existing = state.artifacts.get(artifact_key)
    if existing is None and state.current_stage != rule.completed_stage:
        raise LifecycleError("artifact does not match the active lifecycle stage")

    artifact, preflight = validate_artifact_data(
        rule.artifact_type,
        data,
        allowed_input_roots=allowed_input_roots,
        allowed_output_roots=[workspace.run_directory],
    )
    if not preflight.valid or artifact is None:
        raise LifecycleError("stage artifact failed validation before persistence")
    artifact_path = resolve_within_roots(
        workspace.run_directory / rule.filename,
        [workspace.run_directory],
        must_exist=False,
    )
    payload = json_bytes(artifact.model_dump(mode="json"))
    predicted_hash = sha256_bytes(payload)
    if (
        existing is not None
        and existing.sha256 == predicted_hash
        and artifact_path.is_file()
        and sha256_file(artifact_path) == predicted_hash
    ):
        return state

    atomic_write_bytes(artifact_path, payload)
    _, disk_report = load_artifact_file(
        rule.artifact_type,
        artifact_path,
        allowed_input_roots=allowed_input_roots,
        allowed_output_roots=[workspace.run_directory],
    )
    if not disk_report.valid:
        raise LifecycleError("persisted stage artifact failed validation")
    reference = ArtifactReference(
        artifact_type=rule.artifact_type,
        path=rule.filename,
        sha256=sha256_file(artifact_path),
    )
    updated = invalidate_for_artifact_change(state, artifact_key, reference)
    _write_run_state(workspace, updated)
    _write_summary(workspace, updated)
    return updated


def invalidate_for_artifact_change(
    state: RunState,
    artifact_key: str,
    reference: ArtifactReference,
    *,
    profile_version: str | None = None,
) -> RunState:
    """Replace a validated artifact reference and remove exactly its dependents."""
    if state.status != "running":
        raise LifecycleError("terminal run state cannot be invalidated")
    existing = state.artifacts.get(artifact_key)
    if existing is not None and existing.sha256 == reference.sha256:
        return state
    if artifact_key == "profile":
        if profile_version is None:
            raise LifecycleError("profile invalidation requires the new profile version")
        downstream = _PROFILE_DOWNSTREAM_KEYS
        current_stage: RunStage = "initialized"
        last_completed: RunStage | None = None
    else:
        rule = _ARTIFACT_RULES.get(artifact_key)
        if rule is None:
            raise LifecycleError("artifact key has no invalidation rule")
        if existing is None and state.current_stage != rule.completed_stage:
            raise LifecycleError("artifact does not match the active lifecycle stage")
        downstream = rule.downstream_keys
        current_stage = rule.next_stage
        last_completed = rule.completed_stage

    artifacts = {
        key: value
        for key, value in state.artifacts.items()
        if key not in downstream and key != artifact_key
    }
    artifacts[artifact_key] = reference
    update: dict[str, object] = {
        "artifacts": artifacts,
        "completed_at": None,
        "current_stage": current_stage,
        "failure": None,
        "last_completed_valid_stage": last_completed,
        "status": "running",
    }
    if artifact_key == "profile":
        update["profile_version"] = profile_version
    if artifact_key in {"profile", "collection_request"}:
        update["collection_method"] = None
    if downstream & _FINAL_OUTPUT_KEYS:
        update["final_audio_validation"] = FinalAudioValidation(
            status="pending",
            artifact=None,
            duration_seconds=None,
            message=None,
        )
        update["publication"] = PublicationState(
            status="not_started",
            redacted_locations=[],
            message=None,
        )
    return _validated_state_update(state, update)


def mark_run_failed(
    workspace: RunWorkspace,
    manager: LeaseManager,
    run_id: str,
    *,
    failure: RunFailure,
    now: datetime,
    sensitive_values: Sequence[str] = (),
    feed_token: str | None = None,
) -> RunState:
    """Persist terminal failure and its summary before releasing ownership."""
    try:
        manager.refresh(workspace.episode_key, run_id)
    except LeaseError as error:
        raise LifecycleError(str(error)) from None
    state = load_run_state(workspace.state_path)
    if state.run_id != run_id or state.status != "running":
        raise LifecycleError("only the active run owner may fail running state")
    if failure.stage != state.current_stage:
        raise LifecycleError("failure stage must match the active stage")
    safe_failure = RunFailure(
        stage=failure.stage,
        code=failure.code,
        message=redact_text(
            failure.message,
            sensitive_values=sensitive_values,
            feed_token=feed_token,
        ),
        recovery_guidance=redact_text(
            failure.recovery_guidance,
            sensitive_values=sensitive_values,
            feed_token=feed_token,
        ),
    )
    failed = _failed_state(state, safe_failure, _aware_utc(now))
    _write_run_state(workspace, failed)
    _write_summary(workspace, failed)
    try:
        manager.release(state.episode_key, run_id)
    except LeaseError as error:
        raise LifecycleError(str(error)) from None
    return failed


def load_run_state(path: Path) -> RunState:
    """Load and validate one authoritative run state file."""
    state, report = load_artifact_file("run-state", path)
    if not report.valid or not isinstance(state, RunState):
        raise LifecycleError("run state is missing or invalid")
    return state


def render_summary(workspace: RunWorkspace, state: RunState) -> str:
    """Render the one-screen human recovery surface from authoritative state."""
    audio_valid = state.final_audio_validation.status == "valid"
    publication_succeeded = state.publication.status == "published"
    locations = ", ".join(state.publication.redacted_locations) or "not published"
    warnings: list[str] = []
    if state.final_audio_validation.message:
        warnings.append(state.final_audio_validation.message)
    if state.publication.message:
        warnings.append(state.publication.message)
    warning_text = "; ".join(warnings) if warnings else "none"
    lines = [
        "# Run summary",
        "",
        f"- Overall result: {state.status}",
        f"- Episode: {workspace.episode_title}",
        f"- Episode key: {state.episode_key}",
        f"- Run ID: {state.run_id}",
        f"- Current stage: {state.current_stage}",
        f"- Last completed valid stage: {state.last_completed_valid_stage or 'none'}",
        f"- Valid audio created: {'yes' if audio_valid else 'no'}",
        f"- Publication succeeded: {'yes' if publication_succeeded else 'no'}",
        f"- Output directory: {workspace.run_directory}",
        f"- Published locations: {locations}",
        f"- Warnings: {warning_text}",
    ]
    if state.failure:
        lines.extend(
            [
                f"- Failure: {state.failure.stage}/{state.failure.code} — {state.failure.message}",
                f"- Recovery: {state.failure.recovery_guidance}",
            ]
        )
    return "\n".join(lines) + "\n"


def _initial_state(
    profile: EpisodeProfile,
    profile_path: Path,
    *,
    episode_key: str,
    episode_date: date,
    run_id: str,
    now: datetime,
    repo_root: Path,
    codex_model: str | None,
) -> RunState:
    profile_reference = ArtifactReference(
        artifact_type="profile",
        path=str(profile_path),
        sha256=sha256_file(profile_path),
    )
    return RunState(
        contract_version="1.0",
        prompt_version=None,
        run_id=run_id,
        episode_key=episode_key,
        profile_id=profile.id,
        profile_version=profile.version,
        episode_date=episode_date,
        engine_version=__version__,
        engine_git_commit=_git_commit(repo_root),
        skill_version=SKILL_VERSION,
        prompt_versions={},
        collection_method=None,
        codex_model=codex_model,
        gemini_model=profile.tts.model,
        started_at=now,
        completed_at=None,
        current_stage="initialized",
        last_completed_valid_stage=None,
        status="running",
        failure=None,
        artifacts={"profile": profile_reference},
        final_audio_validation=FinalAudioValidation(
            status="pending",
            artifact=None,
            duration_seconds=None,
            message=None,
        ),
        publication=PublicationState(
            status="not_started",
            redacted_locations=[],
            message=None,
        ),
    )


def _failed_state(state: RunState, failure: RunFailure, now: datetime) -> RunState:
    return _validated_state_update(
        state,
        {
            "completed_at": now,
            "failure": failure,
            "status": "failed",
        },
    )


def _validated_state_update(state: RunState, update: Mapping[str, object]) -> RunState:
    data = state.model_dump(mode="json")
    data.update(update)
    return RunState.model_validate(data)


def _write_run_state(workspace: RunWorkspace, state: RunState) -> None:
    data = state.model_dump(mode="json")
    _, report = validate_artifact_data("run-state", data)
    if not report.valid:
        raise LifecycleError("run state failed validation before persistence")
    atomic_write_json(workspace.state_path, data)
    persisted, disk_report = load_artifact_file("run-state", workspace.state_path)
    if not disk_report.valid or not isinstance(persisted, RunState):
        raise LifecycleError("persisted run state failed validation")


def _write_summary(workspace: RunWorkspace, state: RunState) -> None:
    atomic_write_text(workspace.summary_path, render_summary(workspace, state))


def _create_run_directory(
    runtime_root: Path,
    episode_date: date,
    profile_id: str,
    run_id: str,
) -> Path:
    candidate = runtime_root / "runs" / episode_date.isoformat() / profile_id / run_id
    try:
        resolved = resolve_within_roots(candidate, [runtime_root], must_exist=False)
        resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        resolved.mkdir(mode=0o700, exist_ok=False)
    except (SafetyError, OSError) as error:
        raise LifecycleError("dedicated run directory could not be created safely") from error
    return resolved


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LifecycleError("engine Git commit could not be determined") from error
    return result.stdout.strip()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LifecycleError("lifecycle timestamps must be timezone-aware")
    return value.astimezone(UTC)
