from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import audio_engine.lifecycle as lifecycle_module
from audio_engine.artifacts import (
    CollectionMethod,
    EditorialPlan,
    EpisodeScript,
    EvidenceDossier,
    RunState,
)
from audio_engine.collection import record_collection_attempt
from audio_engine.config import EngineSettings
from audio_engine.editorial import record_editorial_attempt
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    initialize_run,
    load_run_state,
    record_collection_method,
)
from audio_engine.profile import EpisodeProfile, load_profile
from audio_engine.scriptwriting import (
    ScriptwritingError,
    open_script_run,
    record_script_attempt,
)
from audio_engine.storage import StorageError, sha256_file
from audio_engine.validation import (
    render_transcript,
    validate_script_against_plan_and_dossier,
    validate_script_against_profile,
    validate_transcript_projection,
)

ARTIFACT_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
PLAN_ROOT = Path(__file__).parents[1] / "fixtures" / "editorial-plans"
FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)


def _fixed_run_id(profile_id: str, episode_date: date, now: datetime) -> str:
    del now
    return f"{profile_id}_{episode_date.isoformat()}_script"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _ready_script_run(
    profile_path: Path,
    settings_values: dict[str, str],
) -> tuple[RunWorkspace, LeaseManager, RunState, EpisodeProfile, tuple[Path, ...]]:
    settings = EngineSettings.from_mapping(settings_values)
    initialized = initialize_run(
        profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
    )
    assert initialized.run_directory is not None
    state = load_run_state(initialized.run_directory / "state.json")
    workspace = RunWorkspace(
        initialized.run_directory,
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
        json.dumps(_json(ARTIFACT_ROOT / "evidence-dossier.json")), encoding="utf-8"
    )
    collection = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=2),
    )
    assert collection.status == "accepted"
    profile_roots = (Path(settings_values["AUDIO_ENGINE_INPUT_ROOTS"]),)
    profile = load_profile(profile_path, allowed_roots=profile_roots)
    plan_path = workspace.run_directory / "editorial-plan.json"
    plan_path.write_text(json.dumps(_json(ARTIFACT_ROOT / "editorial-plan.json")), encoding="utf-8")
    editorial = record_editorial_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=plan_path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=3),
    )
    assert editorial.status == "accepted"
    return workspace, manager, load_run_state(workspace.state_path), profile, profile_roots


def _write_script(workspace: RunWorkspace, data: dict[str, Any]) -> Path:
    path = workspace.run_directory / "episode-script.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_script_projects_transcript_advances_and_resumes(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_script_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_script(workspace, _json(ARTIFACT_ROOT / "episode-script.json"))

    accepted = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    script_modified_at = path.stat().st_mtime_ns
    resumed = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    final = load_run_state(workspace.state_path)
    persisted = EpisodeScript.model_validate(_json(path))
    transcript_path = workspace.run_directory / "transcript.txt"

    assert accepted.status == "accepted"
    assert accepted.report.warnings == ()
    assert resumed.status == "already_valid"
    assert final.current_stage == "tts"
    assert final.last_completed_valid_stage == "script"
    assert final.prompt_versions["script"] == "1.0.0"
    assert final.script_validation is not None
    assert final.script_validation.status == "valid"
    assert final.artifacts["script_validation"] == final.script_validation.report
    assert final.artifacts["episode_script"].sha256 == sha256_file(path)
    assert final.artifacts["transcript"].sha256 == sha256_file(transcript_path)
    assert persisted.profile == final.artifacts["profile"]
    assert persisted.evidence_dossier == final.artifacts["evidence_dossier"]
    assert persisted.editorial_plan == final.artifacts["editorial_plan"]
    assert transcript_path.read_text(encoding="utf-8") == render_transcript(persisted)
    assert path.stat().st_mtime_ns == script_modified_at


@pytest.mark.parametrize(
    "filename",
    ["episode-script.json", "transcript.txt", "script-validation-attempt-1.json"],
)
def test_verified_resume_rejects_tampered_script_outputs(
    filename: str,
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_script_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_script(workspace, _json(ARTIFACT_ROOT / "episode-script.json"))
    result = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    assert result.status == "accepted"
    tampered = workspace.run_directory / filename
    tampered.write_text(tampered.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ScriptwritingError, match="output hash"):
        record_script_attempt(
            workspace,
            manager,
            state.run_id,
            profile=profile,
            candidate_path=path,
            allowed_profile_roots=profile_roots,
            now=FIXED_NOW + timedelta(minutes=5),
        )


def test_invalid_script_has_one_recorded_repair(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_script_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_script(workspace, {})
    first = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    _write_script(workspace, _json(ARTIFACT_ROOT / "episode-script.json"))
    second = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    final = load_run_state(workspace.state_path)

    assert first.status == "repair_required"
    assert second.status == "accepted"
    assert second.attempt == 2
    assert final.script_validation is not None
    assert final.script_validation.attempt == 2
    assert (workspace.run_directory / "script-validation-attempt-1.json").is_file()
    assert (workspace.run_directory / "script-validation-attempt-2.json").is_file()


def test_second_invalid_script_fails_and_releases_owner(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_script_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_script(workspace, {})
    first = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )
    second = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    failed = load_run_state(workspace.state_path)

    assert first.status == "repair_required"
    assert second.status == "failed"
    assert failed.status == "failed"
    assert failed.failure is not None
    assert failed.failure.code == "script_validation_failed"
    assert not manager.lease_path(state.episode_key).exists()
    assert "no repairs remain" in workspace.summary_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("voice", "speaker_configuration_mismatch"),
        ("url", "spoken_url"),
        ("citation", "spoken_citation"),
        ("personal", "fake_personal_experience"),
        ("analysis_claim", "missing_claim_lineage"),
        ("unknown_claim", "unknown_claim"),
        ("qualification", "missing_qualification"),
        ("attribution", "missing_required_attribution"),
        ("duration", "script_duration_out_of_bounds"),
        ("third_speaker", "schema_error"),
        ("tts_limit", "schema_error"),
        ("planned_coverage", "planned_segment_coverage"),
        ("boundary_mismatch", "script_segment_plan_mismatch"),
        ("required_claim", "missing_required_planned_claim"),
        ("claim_not_planned", "claim_not_planned"),
        ("incomplete_lineage", "incomplete_turn_lineage"),
        ("unknown_segment", "unknown_planned_segment"),
        ("unknown_candidate", "unknown_candidate"),
    ],
)
def test_script_failures_are_machine_readable(
    case: str,
    expected_code: str,
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_script_run(
        synthetic_collection_profile_path, settings_values
    )
    script = _json(ARTIFACT_ROOT / "episode-script.json")
    if case == "voice":
        script["speakers"][0]["voice"] = "different-voice"
    elif case == "url":
        script["turns"][0]["text"] += " Visit https://example.com."
    elif case == "citation":
        script["turns"][0]["text"] += " [1]"
    elif case == "personal":
        script["turns"][0]["text"] += " I read the report myself."
    elif case == "analysis_claim":
        script["turns"][2]["claim_ids"] = []
    elif case == "unknown_claim":
        script["turns"][1]["claim_ids"] = ["claim_missing"]
    elif case == "qualification":
        script["turns"][1]["text"] = (
            "In our synthetic test plot, monitors recorded twelve new habitat clusters."
        )
    elif case == "attribution":
        script["turns"][4]["text"] = (
            "The calibration interval changes from thirty days to fourteen."
        )
    elif case == "duration":
        script["estimated_duration_seconds"] = 60
    elif case == "third_speaker":
        script["speakers"].append({"name": "Third", "voice": "another-voice"})
    elif case == "tts_limit":
        script["segments"][0]["estimated_input_tokens"] = 7001
    elif case == "boundary_mismatch":
        script["segments"][0]["planned_segment_ids"] = ["segment_sensor"]
        script["segments"][1]["planned_segment_ids"] = ["segment_reef"]
    elif case == "required_claim":
        script["turns"][4]["turn_type"] = "question"
        script["turns"][4]["claim_ids"] = []
    elif case == "claim_not_planned":
        script["turns"][1]["claim_ids"] = ["claim_sensor_interval"]
    elif case == "incomplete_lineage":
        script["turns"][1]["candidate_id"] = None
        script["turns"][1]["planned_segment_id"] = None
    elif case == "unknown_segment":
        script["turns"][3]["planned_segment_id"] = "segment_missing"
    elif case == "unknown_candidate":
        script["turns"][3]["candidate_id"] = "item_missing"
    else:
        script["segments"][1]["planned_segment_ids"] = ["segment_reef"]
    path = _write_script(workspace, script)

    result = record_script_attempt(
        workspace,
        manager,
        state.run_id,
        profile=profile,
        candidate_path=path,
        allowed_profile_roots=profile_roots,
        now=FIXED_NOW + timedelta(minutes=4),
    )

    assert result.status == "repair_required"
    assert expected_code in {issue.code for issue in result.report.errors}


@pytest.mark.parametrize(
    ("case", "warning_code"),
    [
        ("tags", "excessive_performance_tags"),
        ("reactions", "excessive_reaction_turns"),
        ("word_share", "host_word_share"),
        ("consecutive", "consecutive_host_turns"),
        ("stock", "repeated_stock_phrase"),
        ("takeaway", "missing_segment_takeaway"),
        ("preferred_duration", "script_duration_preferred"),
    ],
)
def test_script_conversational_warnings(
    case: str,
    warning_code: str,
    synthetic_collection_profile_path: Path,
) -> None:
    profile = load_profile(
        synthetic_collection_profile_path,
        allowed_roots=[synthetic_collection_profile_path.parent],
    )
    script_data = _json(ARTIFACT_ROOT / "episode-script.json")
    editorial_plan_data = _json(ARTIFACT_ROOT / "editorial-plan.json")
    editorial_plan = EditorialPlan.model_validate(editorial_plan_data)
    if case == "tags":
        script_data["turns"][1]["performance_cue"] = "serious"
    elif case == "reactions":
        for index in (0, 3, 5):
            script_data["turns"][index]["turn_type"] = "reaction"
    elif case == "word_share":
        script_data["turns"][0]["text"] += " context" * 200
    elif case == "consecutive":
        for index in range(4):
            script_data["turns"][index]["speaker"] = "Maya"
    elif case == "stock":
        script_data["turns"][0]["text"] += " Absolutely."
        script_data["turns"][3]["text"] += " Absolutely."
    elif case == "takeaway":
        script_data["turns"][2]["turn_type"] = "question"
        script_data["turns"][5]["turn_type"] = "transition"
    else:
        script_data["estimated_duration_seconds"] = 480
    script = EpisodeScript.model_validate(script_data)

    errors, warnings = validate_script_against_profile(script, editorial_plan, profile)

    assert warning_code in {warning.code for warning in warnings}
    if case not in {"consecutive"}:
        assert not errors


def test_fatal_profile_warning_is_promoted_to_error(
    synthetic_collection_profile_path: Path,
) -> None:
    profile_data = load_profile(
        synthetic_collection_profile_path,
        allowed_roots=[synthetic_collection_profile_path.parent],
    ).model_dump(mode="json")
    profile_data["performance"]["fatal_warning_codes"] = ["host_word_share"]
    profile = EpisodeProfile.model_validate(profile_data)
    script_data = _json(ARTIFACT_ROOT / "episode-script.json")
    script_data["turns"][0]["text"] += " context" * 200
    script = EpisodeScript.model_validate(script_data)
    plan = EditorialPlan.model_validate(_json(ARTIFACT_ROOT / "editorial-plan.json"))

    errors, warnings = validate_script_against_profile(script, plan, profile)

    assert "host_word_share" in {error.code for error in errors}
    assert "host_word_share" not in {warning.code for warning in warnings}


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("unused_speaker", "configured_speaker_unused"),
        ("forbidden_cue", "performance_cue_forbidden"),
        ("invalid_cue", "invalid_performance_cue"),
        ("invalid_text", "invalid_spoken_text"),
        ("naked_url", "spoken_url"),
        ("tts_limit", "tts_limit_mismatch"),
    ],
)
def test_script_profile_policy_errors(
    case: str,
    expected_code: str,
    synthetic_collection_profile_path: Path,
) -> None:
    profile_data = load_profile(
        synthetic_collection_profile_path,
        allowed_roots=[synthetic_collection_profile_path.parent],
    ).model_dump(mode="json")
    script_data = _json(ARTIFACT_ROOT / "episode-script.json")
    if case == "unused_speaker":
        for turn in script_data["turns"]:
            turn["speaker"] = "Maya"
    elif case == "forbidden_cue":
        profile_data["performance"]["use_audio_tags"] = "never"
    elif case == "invalid_cue":
        script_data["turns"][0]["performance_cue"] = "[calm]"
    elif case == "invalid_text":
        script_data["turns"][0]["text"] += "\nsecond line"
    elif case == "naked_url":
        script_data["turns"][0]["text"] += " Visit malicious.ai."
    else:
        script_data["safe_input_tokens"] = 6999
    profile = EpisodeProfile.model_validate(profile_data)
    script = EpisodeScript.model_validate(script_data)
    plan = EditorialPlan.model_validate(_json(ARTIFACT_ROOT / "editorial-plan.json"))

    errors, _ = validate_script_against_profile(script, plan, profile)

    assert expected_code in {error.code for error in errors}


def test_disagreement_and_transcript_projection_checks_are_deterministic(
    synthetic_collection_profile_path: Path,
) -> None:
    profile = load_profile(
        synthetic_collection_profile_path,
        allowed_roots=[synthetic_collection_profile_path.parent],
    )
    dossier = EvidenceDossier.model_validate(_json(ARTIFACT_ROOT / "evidence-dossier.json"))
    plan = EditorialPlan.model_validate(_json(PLAN_ROOT / "source-disagreement.json"))
    script_data = _json(ARTIFACT_ROOT / "episode-script.json")
    script_data["turns"][2]["text"] = (
        "The record covers one fictional plot and one interval, so the conclusion stays narrow."
    )
    script = EpisodeScript.model_validate(script_data)

    lineage = validate_script_against_plan_and_dossier(script, plan, dossier)
    profile_errors, _ = validate_script_against_profile(script, plan, profile)
    transcript = render_transcript(script)

    assert "missing_disagreement_treatment" in {issue.code for issue in lineage}
    assert not profile_errors
    assert validate_transcript_projection(script, transcript) == ()
    assert validate_transcript_projection(script, "")[0].code == "empty_transcript"
    assert (
        validate_transcript_projection(script, transcript.replace("twelve", "thirteen"))[0].code
        == "transcript_mismatch"
    )


def test_script_state_write_failure_does_not_advance(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, manager, state, profile, profile_roots = _ready_script_run(
        synthetic_collection_profile_path, settings_values
    )
    path = _write_script(workspace, _json(ARTIFACT_ROOT / "episode-script.json"))

    def fail_state_write(workspace: RunWorkspace, state: RunState) -> None:
        del workspace, state
        raise StorageError("synthetic state failure")

    monkeypatch.setattr(lifecycle_module, "_write_run_state", fail_state_write)

    with pytest.raises(LifecycleError, match="script validation could not be persisted"):
        record_script_attempt(
            workspace,
            manager,
            state.run_id,
            profile=profile,
            candidate_path=path,
            allowed_profile_roots=profile_roots,
            now=FIXED_NOW + timedelta(minutes=4),
        )

    persisted = load_run_state(workspace.state_path)
    assert persisted.current_stage == "script"
    assert persisted.script_validation is None
    assert "episode_script" not in persisted.artifacts
    assert "script_validation" not in persisted.artifacts
    assert "transcript" not in persisted.artifacts


def test_open_script_run_rejects_unknown_workspace(
    tmp_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings = EngineSettings.from_mapping(settings_values)
    with pytest.raises(ScriptwritingError, match="run directory"):
        open_script_run(
            tmp_path / "missing",
            settings=settings,
            repo_root=Path(__file__).parents[2],
        )
