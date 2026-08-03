from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import audio_engine.lifecycle as lifecycle_module
from audio_engine.artifacts import CollectionMethod, RunState
from audio_engine.collection import record_collection_attempt
from audio_engine.config import EngineSettings
from audio_engine.editorial import EditorialError, open_editorial_run, record_editorial_attempt
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    initialize_run,
    load_run_state,
    persist_stage_artifact,
    record_collection_method,
)
from audio_engine.profile import EpisodeProfile, load_profile
from audio_engine.storage import StorageError, sha256_file

ARTIFACT_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
PLAN_ROOT = Path(__file__).parents[1] / "fixtures" / "editorial-plans"
FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)


def _fixed_run_id(profile_id: str, episode_date: date, now: datetime) -> str:
    del now
    return f"{profile_id}_{episode_date.isoformat()}_editorial"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _ready_editorial_run(
    profile_path: Path,
    settings_values: dict[str, str],
) -> tuple[RunWorkspace, LeaseManager, RunState, EpisodeProfile, tuple[Path, ...]]:
    settings = EngineSettings.from_mapping(settings_values)
    result = initialize_run(
        profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
    )
    assert result.run_directory is not None
    state = load_run_state(result.run_directory / "state.json")
    workspace = RunWorkspace(
        result.run_directory,
        f"Synthetic marine research — {state.episode_date}",
        state.episode_key,
    )
    manager = LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6))
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    dossier_path = workspace.run_directory / "evidence-dossier.json"
    dossier_path.write_text(
        json.dumps(_json(ARTIFACT_ROOT / "evidence-dossier.json")),
        encoding="utf-8",
    )
    result = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=2),
    )
    assert result.status == "accepted"
    profile_roots = (Path(settings_values["AUDIO_ENGINE_INPUT_ROOTS"]),)
    profile = load_profile(profile_path, allowed_roots=profile_roots)
    return workspace, manager, load_run_state(workspace.state_path), profile, profile_roots


def _write_plan(workspace: RunWorkspace, data: dict[str, Any]) -> Path:
    path = workspace.run_directory / "editorial-plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_plan_advances_and_verified_resume_is_idempotent(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_plan(workspace, _json(ARTIFACT_ROOT / "editorial-plan.json"))

    accepted = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=3),
    )
    plan_modified_at = path.stat().st_mtime_ns
    resumed = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    final = load_run_state(workspace.state_path)

    assert accepted.status == "accepted"
    assert resumed.status == "already_valid"
    assert final.current_stage == "script"
    assert final.last_completed_valid_stage == "editorial"
    assert final.prompt_versions["editorial"] == "1.0.0"
    assert final.plan_validation is not None
    assert final.plan_validation.status == "valid"
    assert final.artifacts["plan_validation"] == final.plan_validation.report
    assert final.artifacts["editorial_plan"].sha256 == sha256_file(path)
    assert path.stat().st_mtime_ns == plan_modified_at
    persisted_plan = _json(path)
    assert persisted_plan["run_id"] == state.run_id
    assert persisted_plan["profile"] == final.artifacts["profile"].model_dump(mode="json")
    assert persisted_plan["evidence_dossier"] == final.artifacts["evidence_dossier"].model_dump(
        mode="json"
    )


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("editorial-plan.json", "editorial plan hash"),
        ("plan-validation-attempt-1.json", "plan validation hash"),
    ],
)
def test_verified_resume_rejects_tampered_plan_or_report(
    filename: str,
    message: str,
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    plan_path = _write_plan(workspace, _json(ARTIFACT_ROOT / "editorial-plan.json"))
    accepted = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=plan_path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=3),
    )
    assert accepted.status == "accepted"
    tampered = workspace.run_directory / filename
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(EditorialError, match=message):
        record_editorial_attempt(
            workspace,
            manager,
            state.run_id,
            profile=profile,
            candidate_path=plan_path,
            allowed_profile_roots=profile_roots,
            now=FIXED_NOW + timedelta(minutes=4),
        )


def test_invalid_plan_has_one_recorded_repair(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    invalid = _json(PLAN_ROOT / "shorter-useful.json")
    invalid["exclusions"] = []
    path = _write_plan(workspace, invalid)

    first = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=3),
    )
    _write_plan(workspace, _json(PLAN_ROOT / "shorter-useful.json"))
    second = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    final = load_run_state(workspace.state_path)

    assert first.status == "repair_required"
    assert ("candidate_not_dispositioned", "/exclusions") in {
        (issue.code, issue.path) for issue in first.report.errors
    }
    assert second.status == "accepted"
    assert second.attempt == 2
    assert final.plan_validation is not None
    assert final.plan_validation.attempt == 2
    assert (workspace.run_directory / "plan-validation-attempt-1.json").is_file()
    assert (workspace.run_directory / "plan-validation-attempt-2.json").is_file()


def test_second_invalid_plan_fails_and_releases_owner(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_plan(workspace, {})

    first = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=3),
    )
    second = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    failed = load_run_state(workspace.state_path)

    assert first.status == "repair_required"
    assert second.status == "failed"
    assert failed.status == "failed"
    assert failed.failure is not None
    assert failed.failure.code == "plan_validation_failed"
    assert not manager.lease_path(state.episode_key).exists()
    assert "no repairs remain" in workspace.summary_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("duplicate_candidate", "duplicate_selection"),
        ("unknown_claim", "unknown_claim"),
        ("unsupported_section", "unsupported_classification"),
        ("invalid_host", "invalid_lead_host"),
        ("short_duration", "duration_out_of_bounds"),
        ("item_limit", "item_limit_exceeded"),
        ("missing_exclusion_reason", "schema_error"),
    ],
)
def test_plan_policy_failures_are_machine_readable(
    case: str,
    expected_code: str,
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    plan = _json(ARTIFACT_ROOT / "editorial-plan.json")
    if case == "duplicate_candidate":
        plan["segments"][1]["candidate_id"] = "item_reef_plot"
    elif case == "unknown_claim":
        plan["segments"][0]["required_claim_ids"] = ["claim_missing"]
    elif case == "unsupported_section":
        plan["segments"][0]["section"] = "undeclared"
    elif case == "invalid_host":
        plan["segments"][0]["lead_host"] = "Unknown"
    elif case == "short_duration":
        plan["segments"][0]["desired_duration_seconds"] = 30
        plan["segments"][1]["desired_duration_seconds"] = 30
        plan["planned_duration_seconds"] = 60
    elif case == "item_limit":
        segment = copy.deepcopy(plan["segments"][0])
        segment["segment_id"] = "segment_extra"
        segment["order"] = 3
        segment["desired_duration_seconds"] = 60
        plan["segments"].append(segment)
        plan["planned_duration_seconds"] += 60
    else:
        plan["exclusions"].append({})
    path = _write_plan(workspace, plan)

    result = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=3),
    )

    assert result.status == "repair_required"
    assert expected_code in {issue.code for issue in result.report.errors}


def test_replacing_valid_plan_clears_validation_and_requires_revalidation(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_plan(workspace, _json(ARTIFACT_ROOT / "editorial-plan.json"))
    accepted = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=3),
    )
    assert accepted.status == "accepted"

    replacement = json.loads(path.read_text(encoding="utf-8"))
    replacement["segments"][0]["lead_host"] = "Unknown"
    replaced = persist_stage_artifact(
        workspace,
        manager,
        state.run_id,
        artifact_key="editorial_plan",
        data=replacement,
        allowed_input_roots=profile_roots,
    )
    assert replaced.current_stage == "editorial"
    assert replaced.last_completed_valid_stage == "collection"
    assert replaced.plan_validation is None
    assert "plan_validation" not in replaced.artifacts

    invalid = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    assert invalid.status == "repair_required"

    _write_plan(workspace, _json(ARTIFACT_ROOT / "editorial-plan.json"))
    repaired = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    assert repaired.status == "accepted"
    assert repaired.attempt == 2


def test_plan_state_write_failure_does_not_advance(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_plan(workspace, _json(ARTIFACT_ROOT / "editorial-plan.json"))

    def fail_state_write(workspace: RunWorkspace, state: RunState) -> None:
        del workspace, state
        raise StorageError("synthetic state failure")

    monkeypatch.setattr(lifecycle_module, "_write_run_state", fail_state_write)

    with pytest.raises(LifecycleError, match="could not be persisted"):
        record_editorial_attempt(
            workspace,
            manager,
            state.run_id,
            profile=profile,
            candidate_path=path,
            allowed_profile_roots=profile_roots,
            now=FIXED_NOW + timedelta(minutes=3),
        )

    persisted = load_run_state(workspace.state_path)
    assert persisted.current_stage == "editorial"
    assert persisted.plan_validation is None
    assert "editorial_plan" not in persisted.artifacts
    assert "plan_validation" not in persisted.artifacts


def test_open_editorial_run_rejects_unknown_workspace(
    tmp_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings = EngineSettings.from_mapping(settings_values)

    with pytest.raises(EditorialError, match="run directory"):
        open_editorial_run(
            tmp_path / "missing",
            settings=settings,
            repo_root=Path(__file__).parents[2],
        )


def test_editorial_timestamp_must_be_timezone_aware(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_editorial_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_plan(workspace, _json(ARTIFACT_ROOT / "editorial-plan.json"))

    with pytest.raises(EditorialError, match="timezone-aware"):
        record_editorial_attempt(
            workspace,
            manager,
            state.run_id,
            profile=profile,
            candidate_path=path,
            allowed_profile_roots=profile_roots,
            now=datetime(2026, 1, 15, 15, 3),
        )
