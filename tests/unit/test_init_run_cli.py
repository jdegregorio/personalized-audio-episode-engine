from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.init_run import main

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


def _install_fake_environment(
    monkeypatch: pytest.MonkeyPatch, settings_values: dict[str, str]
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in settings_values.items():
        monkeypatch.setenv(name, value)


def test_init_run_cli_initializes_then_reports_noop(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_fake_environment(monkeypatch, settings_values)

    first = main(["--profile", str(synthetic_profile_path), "--codex-model", "synthetic"])
    first_output = json.loads(capsys.readouterr().out)
    second = main(["--profile", str(synthetic_profile_path)])
    second_output = json.loads(capsys.readouterr().out)

    assert first == 0
    assert first_output["result"] == "initialized"
    assert second == 0
    assert second_output["result"] == "no_op"
    assert second_output["run_directory"] is None


def test_init_run_cli_reports_missing_settings_without_values(
    synthetic_profile_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    result = main(["--profile", str(synthetic_profile_path)])

    output = json.loads(capsys.readouterr().err)
    assert result == 1
    assert output["code"] == "invalid_settings"
    assert "GEMINI_API_KEY" in output["fields"]
    assert "value" not in output


def test_init_run_cli_reports_invalid_profile_without_traceback(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_fake_environment(monkeypatch, settings_values)
    synthetic_profile_path.write_text("schema_version: [invalid", encoding="utf-8")

    result = main(["--profile", str(synthetic_profile_path)])

    captured = capsys.readouterr()
    output = json.loads(captured.err)
    assert result == 1
    assert output["code"] == "initialization_failed"
    assert "traceback" not in captured.err.lower()
    assert captured.out == ""
