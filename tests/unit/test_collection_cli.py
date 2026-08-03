from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import initialize_run, load_run_state
from scripts.record_collection import main as record_main
from scripts.select_collection_method import main as select_main

FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
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
    return f"{profile_id}_{episode_date.isoformat()}_cli"


def _environment(
    monkeypatch: pytest.MonkeyPatch,
    settings_values: dict[str, str],
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in settings_values.items():
        monkeypatch.setenv(name, value)


def _initialize(
    profile_path: Path,
    settings_values: dict[str, str],
) -> tuple[Path, str]:
    result = initialize_run(
        profile_path,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
    )
    assert result.run_directory is not None
    assert result.run_id is not None
    return result.run_directory, result.run_id


def test_select_cli_records_specialized_failure_and_native_fallback(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory, _ = _initialize(synthetic_collection_profile_path, settings_values)

    selected = select_main(
        [
            "--run",
            str(run_directory),
            "--capability",
            "web_deep_research=1.2.0",
            "--preferred-capability",
            "web_deep_research",
        ]
    )
    specialized = json.loads(capsys.readouterr().out)
    fallback_result = select_main(
        [
            "--run",
            str(run_directory),
            "--capability",
            "web_deep_research=1.2.0",
            "--failed-capability",
            "web_deep_research",
        ]
    )
    fallback = json.loads(capsys.readouterr().out)
    persisted_result = select_main(
        [
            "--run",
            str(run_directory),
            "--capability",
            "web_deep_research=1.2.0",
        ]
    )
    persisted = json.loads(capsys.readouterr().out)
    state = load_run_state(run_directory / "state.json")

    assert selected == 0
    assert specialized["collection_method"]["type"] == "specialized_capability"
    assert fallback_result == 0
    assert fallback["collection_method"]["type"] == "native_research"
    assert fallback["failed_capabilities"] == ["web_deep_research"]
    assert persisted_result == 0
    assert persisted["collection_method"]["type"] == "native_research"
    assert state.collection_method is not None
    assert state.collection_method.type == "native_research"
    assert state.failed_collection_capabilities == ["web_deep_research"]


def test_select_cli_terminalizes_missing_required_capability(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = yaml.safe_load(synthetic_collection_profile_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    data["collection"]["required_capabilities"] = ["authenticated_archive"]
    synthetic_collection_profile_path.write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    _environment(monkeypatch, settings_values)
    run_directory, run_id = _initialize(synthetic_collection_profile_path, settings_values)

    result = select_main(["--run", str(run_directory)])

    output = json.loads(capsys.readouterr().err)
    state = load_run_state(run_directory / "state.json")
    manager = LeaseManager(
        EngineSettings.from_mapping(settings_values).runtime_root,
        maximum_age=timedelta(hours=6),
    )
    assert result == 1
    assert output["code"] == "collection_capability_unavailable"
    assert "authenticated_archive" in output["message"]
    assert state.status == "failed"
    assert state.failure is not None
    assert state.failure.code == "collection_capability_unavailable"
    assert not manager.lease_path(state.episode_key).exists()
    assert state.run_id == run_id


def test_record_cli_accepts_method_neutral_dossier(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory, _ = _initialize(synthetic_collection_profile_path, settings_values)
    assert select_main(["--run", str(run_directory)]) == 0
    capsys.readouterr()
    dossier = json.loads((FIXTURE_ROOT / "evidence-dossier.json").read_text(encoding="utf-8"))
    (run_directory / "evidence-dossier.json").write_text(json.dumps(dossier), encoding="utf-8")

    result = record_main(["--run", str(run_directory)])

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["status"] == "accepted"
    assert output["valid"] is True


def test_record_cli_reports_invalid_settings_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    result = record_main(["--run", str(tmp_path)])

    output = json.loads(capsys.readouterr().err)
    assert result == 1
    assert output["code"] == "invalid_settings"
    assert "value" not in output


def test_record_cli_reports_missing_method_then_one_repair(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _environment(monkeypatch, settings_values)
    run_directory, _ = _initialize(synthetic_collection_profile_path, settings_values)

    missing_method = record_main(["--run", str(run_directory)])
    missing_output = json.loads(capsys.readouterr().err)
    assert select_main(["--run", str(run_directory)]) == 0
    capsys.readouterr()
    (run_directory / "evidence-dossier.json").write_text("{}", encoding="utf-8")
    invalid = record_main(["--run", str(run_directory)])
    invalid_output = json.loads(capsys.readouterr().err)

    assert missing_method == 1
    assert missing_output["code"] == "collection_record_failed"
    assert invalid == 1
    assert invalid_output["status"] == "repair_required"
    assert invalid_output["attempt"] == 1
