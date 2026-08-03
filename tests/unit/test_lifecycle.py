from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import audio_engine.lifecycle as lifecycle_module
from audio_engine.artifacts import ArtifactReference, RunFailure, RunState
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    canonical_episode_key,
    generate_run_id,
    initialize_run,
    invalidate_for_artifact_change,
    load_run_state,
    mark_run_failed,
    persist_stage_artifact,
)
from audio_engine.storage import StorageError, sha256_file

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)


def _settings(values: dict[str, str]) -> EngineSettings:
    return EngineSettings.from_mapping(values)


def _fixed_run_id(profile_id: str, episode_date: date, now: datetime) -> str:
    del now
    return f"{profile_id}_{episode_date.isoformat()}_fixed"


def _initialize(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> tuple[EngineSettings, RunWorkspace, RunState]:
    settings = _settings(settings_values)
    result = initialize_run(
        synthetic_profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
        codex_model="synthetic-codex",
    )
    assert result.run_directory is not None
    workspace = RunWorkspace(
        result.run_directory,
        "Synthetic lifecycle — 2026-01-15",
        result.episode_key,
    )
    return settings, workspace, load_run_state(workspace.state_path)


def _json(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _evidence_for(state: RunState) -> dict[str, Any]:
    data = _json("evidence-dossier.json")
    data["collection_request"] = state.artifacts["collection_request"].model_dump(mode="json")
    return data


def _plan_for(state: RunState) -> dict[str, Any]:
    data = _json("editorial-plan.json")
    data["run_id"] = state.run_id
    data["profile_id"] = state.profile_id
    data["episode_date"] = state.episode_date.isoformat() if state.episode_date else "2026-01-15"
    data["profile"] = state.artifacts["profile"].model_dump(mode="json")
    data["evidence_dossier"] = state.artifacts["evidence_dossier"].model_dump(mode="json")
    return data


def _script_for(state: RunState) -> dict[str, Any]:
    data = _json("episode-script.json")
    data["run_id"] = state.run_id
    data["profile_id"] = state.profile_id
    data["episode_date"] = state.episode_date.isoformat() if state.episode_date else "2026-01-15"
    data["profile"] = state.artifacts["profile"].model_dump(mode="json")
    data["evidence_dossier"] = state.artifacts["evidence_dossier"].model_dump(mode="json")
    data["editorial_plan"] = state.artifacts["editorial_plan"].model_dump(mode="json")
    return data


def _reference(artifact_type: str, path: str, character: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_type=artifact_type,
        path=path,
        sha256=f"sha256:{character * 64}",
    )


def test_canonical_key_and_run_ids_are_stable_and_unique() -> None:
    episode_date = date(2026, 1, 15)

    identifiers = {
        generate_run_id("synthetic-lifecycle", episode_date, now=FIXED_NOW) for _ in range(50)
    }

    assert canonical_episode_key("synthetic-lifecycle", episode_date) == (
        "synthetic-lifecycle:2026-01-15"
    )
    assert len(identifiers) == 50
    assert all(
        identifier.startswith("synthetic-lifecycle_2026-01-15_") for identifier in identifiers
    )


def test_additive_state_provenance_is_compatible_and_cross_checked() -> None:
    data = _json("run-state.json")
    data.pop("episode_date")
    data.pop("engine_version")

    legacy = RunState.model_validate(data)

    assert legacy.episode_date is None
    assert legacy.engine_version is None

    data["episode_date"] = "2026-01-16"
    with pytest.raises(ValueError, match="episode key"):
        RunState.model_validate(data)


def test_initialize_run_creates_valid_request_state_summary_and_layout(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, state = _initialize(synthetic_profile_path, settings_values)
    request_path = workspace.run_directory / "collection-request.json"
    summary = workspace.summary_path.read_text(encoding="utf-8")

    assert workspace.run_directory.relative_to(settings.runtime_root).parts[:3] == (
        "runs",
        "2026-01-15",
        "synthetic-lifecycle",
    )
    assert request_path.is_file()
    assert state.status == "running"
    assert state.current_stage == "collection"
    assert state.last_completed_valid_stage == "initialized"
    assert state.episode_date == date(2026, 1, 15)
    assert state.engine_version == "0.1.0"
    assert state.codex_model == "synthetic-codex"
    assert state.gemini_model
    assert state.artifacts["profile"].sha256 == sha256_file(synthetic_profile_path)
    assert state.artifacts["collection_request"].sha256 == sha256_file(request_path)
    assert "Overall result: running" in summary
    assert "Last completed valid stage: initialized" in summary
    assert "Valid audio created: no" in summary
    assert "Publication succeeded: no" in summary
    assert workspace.state_path.stat().st_mode & 0o777 == 0o600
    assert workspace.summary_path.stat().st_mode & 0o777 == 0o600


def test_second_initialization_is_noop_without_new_run_artifacts(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, _ = _initialize(synthetic_profile_path, settings_values)
    before = sorted(
        path.relative_to(settings.runtime_root) for path in settings.runtime_root.rglob("*")
    )

    second = initialize_run(
        synthetic_profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW + timedelta(minutes=1),
        run_id_factory=lambda profile_id, day, now: f"{profile_id}_{day}_second",
    )

    after = sorted(
        path.relative_to(settings.runtime_root) for path in settings.runtime_root.rglob("*")
    )
    assert second.result == "no_op"
    assert second.run_id is None
    assert second.run_directory is None
    assert before == after
    assert workspace.state_path.exists()


def test_initialization_failure_persists_terminal_recovery_and_releases_lease(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(settings_values)

    def fail_request(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise LifecycleError("synthetic request failure")

    monkeypatch.setattr(lifecycle_module, "build_collection_request", fail_request)

    with pytest.raises(LifecycleError, match="inspect the run summary"):
        initialize_run(
            synthetic_profile_path,
            settings=settings,
            repo_root=Path(__file__).parents[2],
            clock=lambda: FIXED_NOW,
            run_id_factory=_fixed_run_id,
        )

    state_path = next(settings.runtime_root.rglob("state.json"))
    state = load_run_state(state_path)
    summary = state_path.with_name("summary.md").read_text(encoding="utf-8")
    manager = LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6))
    assert state.status == "failed"
    assert state.failure is not None
    assert state.failure.code == "initialization_failed"
    assert "Recovery:" in summary
    assert not manager.lease_path(state.episode_key).exists()


def test_initial_state_validation_failure_happens_before_lease_or_workspace(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings = _settings(settings_values)

    with pytest.raises(LifecycleError):
        initialize_run(
            synthetic_profile_path,
            settings=settings,
            repo_root=Path(__file__).parents[2],
            clock=lambda: FIXED_NOW,
            run_id_factory=_fixed_run_id,
            codex_model="x" * 501,
        )

    assert not list(settings.runtime_root.rglob("episode-*.json"))
    assert not list(settings.runtime_root.rglob("state.json"))
    assert not list(settings.runtime_root.rglob("summary.md"))


def test_persisted_stage_artifact_advances_only_after_validation_and_hashing(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, _ = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=1),
    )
    run_id = load_run_state(workspace.state_path).run_id

    updated = persist_stage_artifact(
        workspace,
        manager,
        run_id,
        artifact_key="evidence_dossier",
        data=_evidence_for(load_run_state(workspace.state_path)),
    )

    evidence_path = workspace.run_directory / "evidence-dossier.json"
    assert updated.current_stage == "editorial"
    assert updated.last_completed_valid_stage == "collection"
    assert updated.artifacts["evidence_dossier"].sha256 == sha256_file(evidence_path)
    assert load_run_state(workspace.state_path) == updated


def test_rewriting_identical_validated_artifact_is_idempotent(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, before = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=1),
    )
    request_path = workspace.run_directory / "collection-request.json"
    modified_at = request_path.stat().st_mtime_ns
    workspace.summary_path.write_text("stale summary\n", encoding="utf-8")

    after = persist_stage_artifact(
        workspace,
        manager,
        before.run_id,
        artifact_key="collection_request",
        data=json.loads(request_path.read_text(encoding="utf-8")),
    )

    assert after == before
    assert request_path.stat().st_mtime_ns == modified_at
    assert "Current stage: collection" in workspace.summary_path.read_text(encoding="utf-8")


def test_stage_artifacts_must_bind_identity_and_upstream_hashes(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, state = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=1),
    )

    request_path = workspace.run_directory / "collection-request.json"
    request_bytes = request_path.read_bytes()
    request_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(LifecycleError, match="hash does not match"):
        persist_stage_artifact(
            workspace,
            manager,
            state.run_id,
            artifact_key="evidence_dossier",
            data=_evidence_for(state),
        )
    request_path.write_bytes(request_bytes)

    with pytest.raises(LifecycleError, match="inputs do not match"):
        persist_stage_artifact(
            workspace,
            manager,
            state.run_id,
            artifact_key="evidence_dossier",
            data=_json("evidence-dossier.json"),
        )
    state = persist_stage_artifact(
        workspace,
        manager,
        state.run_id,
        artifact_key="evidence_dossier",
        data=_evidence_for(state),
    )

    mismatched_plan = _plan_for(state)
    mismatched_plan["evidence_dossier"] = _reference(
        "evidence", "evidence-dossier.json", "0"
    ).model_dump(mode="json")
    with pytest.raises(LifecycleError, match="inputs do not match"):
        persist_stage_artifact(
            workspace,
            manager,
            state.run_id,
            artifact_key="editorial_plan",
            data=mismatched_plan,
            allowed_input_roots=[synthetic_profile_path.parent],
        )
    state = persist_stage_artifact(
        workspace,
        manager,
        state.run_id,
        artifact_key="editorial_plan",
        data=_plan_for(state),
        allowed_input_roots=[synthetic_profile_path.parent],
    )

    mismatched_script = _script_for(state)
    mismatched_script["editorial_plan"] = _reference("plan", "editorial-plan.json", "0").model_dump(
        mode="json"
    )
    with pytest.raises(LifecycleError, match="inputs do not match"):
        persist_stage_artifact(
            workspace,
            manager,
            state.run_id,
            artifact_key="episode_script",
            data=mismatched_script,
            allowed_input_roots=[synthetic_profile_path.parent],
        )
    final = persist_stage_artifact(
        workspace,
        manager,
        state.run_id,
        artifact_key="episode_script",
        data=_script_for(state),
        allowed_input_roots=[synthetic_profile_path.parent],
    )

    assert final.current_stage == "tts"
    assert final.last_completed_valid_stage == "script"


def test_artifact_write_failure_does_not_advance_state(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, workspace, before = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=1),
    )

    def fail_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
        del path, payload, mode
        raise StorageError("synthetic atomic failure")

    monkeypatch.setattr(lifecycle_module, "atomic_write_bytes", fail_write)

    with pytest.raises(StorageError, match="synthetic"):
        persist_stage_artifact(
            workspace,
            manager,
            before.run_id,
            artifact_key="evidence_dossier",
            data=_evidence_for(before),
        )

    after = load_run_state(workspace.state_path)
    assert after.current_stage == "collection"
    assert "evidence_dossier" not in after.artifacts


def test_invalid_stage_artifact_does_not_write_or_advance_state(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, before = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=1),
    )
    invalid_evidence = _evidence_for(before)
    invalid_evidence["candidates"][0]["claim_ids"] = ["claim-does-not-exist"]

    with pytest.raises(LifecycleError, match="failed validation"):
        persist_stage_artifact(
            workspace,
            manager,
            before.run_id,
            artifact_key="evidence_dossier",
            data=invalid_evidence,
        )

    assert not (workspace.run_directory / "evidence-dossier.json").exists()
    assert load_run_state(workspace.state_path) == before


def test_out_of_order_stage_artifact_does_not_write_or_advance_state(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, before = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=1),
    )

    with pytest.raises(LifecycleError, match="active lifecycle stage"):
        persist_stage_artifact(
            workspace,
            manager,
            before.run_id,
            artifact_key="editorial_plan",
            data=_json("editorial-plan.json"),
        )

    assert not (workspace.run_directory / "editorial-plan.json").exists()
    assert load_run_state(workspace.state_path) == before


def test_non_owner_cannot_write_stage_artifact(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, _ = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6))

    with pytest.raises(LifecycleError, match="another run"):
        persist_stage_artifact(
            workspace,
            manager,
            "run_intruder",
            artifact_key="evidence_dossier",
            data=_json("evidence-dossier.json"),
        )

    assert not (workspace.run_directory / "evidence-dossier.json").exists()


@pytest.mark.parametrize(
    ("changed_key", "expected_keys", "expected_current", "expected_last"),
    [
        ("profile", {"profile"}, "initialized", None),
        (
            "evidence_dossier",
            {"profile", "collection_request", "evidence_dossier"},
            "collection",
            "initialized",
        ),
        (
            "editorial_plan",
            {
                "profile",
                "collection_request",
                "evidence_dossier",
                "evidence_validation",
                "editorial_plan",
            },
            "editorial",
            "collection",
        ),
        (
            "episode_script",
            {
                "profile",
                "collection_request",
                "evidence_dossier",
                "evidence_validation",
                "editorial_plan",
                "plan_validation",
                "episode_script",
            },
            "script",
            "editorial",
        ),
    ],
)
def test_artifact_change_invalidates_exact_downstream_dependencies(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
    changed_key: str,
    expected_keys: set[str],
    expected_current: str,
    expected_last: str | None,
) -> None:
    _, _, initial = _initialize(synthetic_profile_path, settings_values)
    data = initial.model_dump(mode="json")
    data["current_stage"] = "publication"
    data["last_completed_valid_stage"] = "audio"
    data["artifacts"] = {
        "profile": _reference("profile", "profile.yaml", "a").model_dump(mode="json"),
        "collection_request": _reference(
            "collection-request", "collection-request.json", "b"
        ).model_dump(mode="json"),
        "evidence_dossier": _reference("evidence", "evidence-dossier.json", "c").model_dump(
            mode="json"
        ),
        "evidence_validation": _reference("validation", "evidence-validation.json", "d").model_dump(
            mode="json"
        ),
        "editorial_plan": _reference("plan", "editorial-plan.json", "e").model_dump(mode="json"),
        "plan_validation": _reference("validation", "plan-validation.json", "f").model_dump(
            mode="json"
        ),
        "episode_script": _reference("script", "episode-script.json", "1").model_dump(mode="json"),
        "script_validation": _reference("validation", "script-validation.json", "2").model_dump(
            mode="json"
        ),
        "transcript": _reference("transcript", "transcript.txt", "3").model_dump(mode="json"),
        "tts_manifest": _reference("tts-manifest", "tts/manifest.json", "4").model_dump(
            mode="json"
        ),
        "final_audio": _reference("audio", "episode.mp3", "5").model_dump(mode="json"),
        "show_notes": _reference("show-notes", "show-notes.html", "6").model_dump(mode="json"),
        "published_episode": _reference(
            "published-episode", "published-episode.json", "7"
        ).model_dump(mode="json"),
    }
    data["tts_preparation"] = {
        "status": "prepared",
        "segment_count": 2,
        "episode_script": data["artifacts"]["episode_script"],
        "transcript": data["artifacts"]["transcript"],
        "manifest": data["artifacts"]["tts_manifest"],
    }
    data["tts_rendering"] = {
        "status": "in_progress",
        "segment_count": 2,
        "completed_segments": [
            {
                "segment_id": "tts_segment_001",
                "order": 1,
                "prompt": _reference("tts-prompt", "tts/segment-001.json", "8").model_dump(
                    mode="json"
                ),
                "raw_audio": _reference(
                    "tts-raw-audio", "tts/audio/segment-001.pcm", "9"
                ).model_dump(mode="json"),
                "audio": _reference("tts-audio", "tts/audio/segment-001.wav", "a").model_dump(
                    mode="json"
                ),
                "provider_media_type": "audio/L16;rate=24000",
                "sample_rate_hz": 24000,
                "channels": 1,
                "sample_width_bytes": 2,
                "duration_seconds": 20.0,
                "request_attempts": 1,
                "completed_at": FIXED_NOW.isoformat(),
            }
        ],
        "failed_segment_id": None,
        "message": None,
        "recovery_guidance": None,
    }
    state = RunState.model_validate(data)
    old = state.artifacts[changed_key]
    replacement = ArtifactReference(
        artifact_type=old.artifact_type,
        path=old.path,
        sha256="sha256:" + "9" * 64,
    )

    updated = invalidate_for_artifact_change(
        state,
        changed_key,
        replacement,
        profile_version="0.2.0" if changed_key == "profile" else None,
    )

    assert set(updated.artifacts) == expected_keys
    assert updated.current_stage == expected_current
    assert updated.last_completed_valid_stage == expected_last
    assert updated.final_audio_validation.status == "pending"
    assert updated.publication.status == "not_started"
    assert updated.tts_preparation is None
    assert updated.tts_rendering is None
    if changed_key == "profile":
        assert updated.profile_version == "0.2.0"
        assert updated.collection_method is None


def test_same_artifact_hash_preserves_downstream_state(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    _, _, state = _initialize(synthetic_profile_path, settings_values)
    existing = state.artifacts["collection_request"]

    assert invalidate_for_artifact_change(state, "collection_request", existing) is state


def test_failure_is_redacted_summarized_and_releases_lease(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, state = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=2),
    )
    secret = "super-secret-runtime-value"

    failed = mark_run_failed(
        workspace,
        manager,
        state.run_id,
        failure=RunFailure(
            stage="collection",
            code="collection_failed",
            message=f"Provider rejected {secret}.",
            recovery_guidance=f"Replace {secret} and retry collection.",
        ),
        now=FIXED_NOW + timedelta(minutes=2),
        sensitive_values=[secret],
    )

    summary = workspace.summary_path.read_text(encoding="utf-8")
    persisted = workspace.state_path.read_text(encoding="utf-8")
    assert failed.status == "failed"
    assert "Recovery:" in summary
    assert secret not in summary
    assert secret not in persisted
    assert "<redacted>" in summary
    assert not manager.lease_path(state.episode_key).exists()


def test_failure_for_wrong_stage_does_not_mutate_or_release(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings, workspace, before = _initialize(synthetic_profile_path, settings_values)
    manager = LeaseManager(
        settings.runtime_root,
        maximum_age=timedelta(hours=6),
        clock=lambda: FIXED_NOW + timedelta(minutes=2),
    )

    with pytest.raises(LifecycleError, match="active stage"):
        mark_run_failed(
            workspace,
            manager,
            before.run_id,
            failure=RunFailure(
                stage="script",
                code="wrong_stage",
                message="Synthetic failure.",
                recovery_guidance="Return to the active stage.",
            ),
            now=FIXED_NOW + timedelta(minutes=2),
        )

    assert load_run_state(workspace.state_path) == before
    assert manager.lease_path(before.episode_key).exists()
