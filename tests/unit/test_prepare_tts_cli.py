from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import audio_engine.lifecycle as lifecycle_module
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import initialize_run, load_run_state
from audio_engine.storage import StorageError
from scripts.prepare_tts import main as prepare_tts_main
from scripts.record_collection import main as record_collection_main
from scripts.record_editorial_plan import main as record_editorial_main
from scripts.record_script import main as record_script_main
from scripts.select_collection_method import main as select_main

FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)
ARTIFACT_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
_SETTING_NAMES = {
    "GEMINI_API_KEY",
    "PODCAST_FEED_TOKEN",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "R2_BUCKET_NAME",
    "PODCAST_BASE_URL",
    "R2_RETENTION_DAYS",
    "AUDIO_ENGINE_RUNTIME_ROOT",
    "AUDIO_ENGINE_STAGING_ROOT",
    "AUDIO_ENGINE_INPUT_ROOTS",
    "AUDIO_ENGINE_MAX_RUN_AGE_SECONDS",
}


def _fixed_run_id(profile_id: str, episode_date: date, now: datetime) -> str:
    del now
    return f"{profile_id}_{episode_date.isoformat()}_tts_cli"


def _environment(
    monkeypatch: pytest.MonkeyPatch,
    settings_values: dict[str, str],
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in settings_values.items():
        monkeypatch.setenv(name, value)


def _ready_run(profile_path: Path, settings_values: dict[str, str]) -> Path:
    result = initialize_run(
        profile_path,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
    )
    assert result.run_directory is not None
    assert select_main(["--run", str(result.run_directory)]) == 0
    dossier = json.loads((ARTIFACT_ROOT / "evidence-dossier.json").read_text(encoding="utf-8"))
    (result.run_directory / "evidence-dossier.json").write_text(
        json.dumps(dossier), encoding="utf-8"
    )
    assert record_collection_main(["--run", str(result.run_directory)]) == 0
    plan = json.loads((ARTIFACT_ROOT / "editorial-plan.json").read_text(encoding="utf-8"))
    (result.run_directory / "editorial-plan.json").write_text(json.dumps(plan), encoding="utf-8")
    assert record_editorial_main(["--run", str(result.run_directory)]) == 0
    script = json.loads((ARTIFACT_ROOT / "episode-script.json").read_text(encoding="utf-8"))
    (result.run_directory / "episode-script.json").write_text(json.dumps(script), encoding="utf-8")
    assert record_script_main(["--run", str(result.run_directory)]) == 0
    return result.run_directory


def test_prepare_tts_cli_prepares_and_resumes_without_rewriting(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory = _ready_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()

    prepared_status = prepare_tts_main(["--run", str(run_directory)])
    prepared = json.loads(capsys.readouterr().out)
    manifest_path = run_directory / "tts" / "manifest.json"
    prompt_paths = sorted((run_directory / "tts").glob("segment-*.json"))
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in [manifest_path, *prompt_paths, run_directory / "state.json"]
    }
    resumed_status = prepare_tts_main(["--run", str(run_directory)])
    resumed = json.loads(capsys.readouterr().out)
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in [manifest_path, *prompt_paths, run_directory / "state.json"]
    }
    state = load_run_state(run_directory / "state.json")

    assert prepared_status == 0
    assert prepared == {
        "manifest": "tts/manifest.json",
        "maximum_estimated_input_tokens": 402,
        "segment_count": 2,
        "status": "prepared",
    }
    assert resumed_status == 0
    assert resumed["status"] == "already_prepared"
    assert before == after
    assert state.current_stage == "tts"
    assert state.tts_preparation is not None
    assert state.tts_preparation.segment_count == 2
    assert state.artifacts["tts_manifest"] == state.tts_preparation.manifest


def test_prepare_tts_cli_rejects_tampered_prompt_on_resume(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory = _ready_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()
    assert prepare_tts_main(["--run", str(run_directory)]) == 0
    capsys.readouterr()
    prompt_path = run_directory / "tts" / "segment-001.json"
    prompt_path.write_text(prompt_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    status = prepare_tts_main(["--run", str(run_directory)])
    error = json.loads(capsys.readouterr().err)

    assert status == 1
    assert error["code"] == "tts_preparation_failed"
    assert "hash no longer matches" in error["message"]


def test_prepare_tts_state_write_failure_is_recoverable(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory = _ready_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()

    def fail_state_write(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise StorageError("synthetic state write failure")

    with monkeypatch.context() as state_write_patch:
        state_write_patch.setattr(lifecycle_module, "_write_run_state", fail_state_write)
        failed_status = prepare_tts_main(["--run", str(run_directory)])
        failure = json.loads(capsys.readouterr().err)
        state_after_failure = load_run_state(run_directory / "state.json")
    recovered_status = prepare_tts_main(["--run", str(run_directory)])
    recovered = json.loads(capsys.readouterr().out)

    assert failed_status == 1
    assert failure["code"] == "tts_preparation_failed"
    assert state_after_failure.tts_preparation is None
    assert (run_directory / "tts" / "manifest.json").is_file()
    assert recovered_status == 0
    assert recovered["status"] == "prepared"


def test_prepare_tts_cli_requires_an_accepted_script(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    result = initialize_run(
        synthetic_collection_profile_path,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
    )
    assert result.run_directory is not None
    capsys.readouterr()

    status = prepare_tts_main(["--run", str(result.run_directory)])
    error = json.loads(capsys.readouterr().err)

    assert status == 1
    assert error["code"] == "tts_preparation_failed"
    assert "valid script" in error["message"]


def test_prepare_tts_cli_reports_invalid_settings_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    status = prepare_tts_main(["--run", str(tmp_path)])
    error = json.loads(capsys.readouterr().err)

    assert status == 1
    assert error["code"] == "invalid_settings"
    assert "value" not in error
