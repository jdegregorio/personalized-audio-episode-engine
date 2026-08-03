from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from audio_engine.config import EngineSettings
from audio_engine.lifecycle import initialize_run, load_run_state
from scripts.record_collection import main as record_collection_main
from scripts.record_editorial_plan import main as record_editorial_main
from scripts.select_collection_method import main as select_main

FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)
ARTIFACT_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
PLAN_ROOT = Path(__file__).parents[1] / "fixtures" / "editorial-plans"
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
    return f"{profile_id}_{episode_date.isoformat()}_editorial_cli"


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
    return result.run_directory


def test_record_editorial_cli_accepts_and_resumes(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory = _ready_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()
    plan = json.loads((ARTIFACT_ROOT / "editorial-plan.json").read_text(encoding="utf-8"))
    (run_directory / "editorial-plan.json").write_text(json.dumps(plan), encoding="utf-8")

    accepted_status = record_editorial_main(["--run", str(run_directory)])
    accepted = json.loads(capsys.readouterr().out)
    resumed_status = record_editorial_main(["--run", str(run_directory)])
    resumed = json.loads(capsys.readouterr().out)
    state = load_run_state(run_directory / "state.json")

    assert accepted_status == 0
    assert accepted["status"] == "accepted"
    assert resumed_status == 0
    assert resumed["status"] == "already_valid"
    assert state.current_stage == "script"


def test_record_editorial_cli_reports_one_repair(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory = _ready_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()
    invalid = json.loads((PLAN_ROOT / "shorter-useful.json").read_text(encoding="utf-8"))
    invalid["exclusions"] = []
    (run_directory / "editorial-plan.json").write_text(json.dumps(invalid), encoding="utf-8")

    result = record_editorial_main(["--run", str(run_directory)])
    output = json.loads(capsys.readouterr().err)

    assert result == 1
    assert output["status"] == "repair_required"
    assert output["attempt"] == 1
    assert output["errors"][0]["code"] == "candidate_not_dispositioned"


def test_record_editorial_cli_reports_invalid_settings_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    result = record_editorial_main(["--run", str(tmp_path)])
    output = json.loads(capsys.readouterr().err)

    assert result == 1
    assert output["code"] == "invalid_settings"
    assert "value" not in output
