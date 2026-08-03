from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

import scripts.assemble_audio as assemble_script
from audio_engine.artifacts import ArtifactReference, FinalAudioValidation
from audio_engine.audio import AudioAssemblyError, AudioAssemblyResult, AudioRunContext
from audio_engine.config import EngineSettings
from scripts.assemble_audio import main
from tests.tts_support import SETTING_NAMES, configure_environment


def _result() -> AudioAssemblyResult:
    return AudioAssemblyResult(
        "assembled",
        FinalAudioValidation(
            status="valid",
            artifact=ArtifactReference(
                artifact_type="audio",
                path="episode.mp3",
                sha256="sha256:" + "a" * 64,
            ),
            media_type="audio/mpeg",
            codec="mp3",
            duration_seconds=42.25,
            sample_rate_hz=48_000,
            channels=1,
            bytes=512_000,
            decode_status="passed",
            message="Final MP3 passed validation.",
        ),
    )


def test_assemble_audio_cli_reports_validation_summary(
    tmp_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)

    def open_run(
        run_directory: Path,
        *,
        settings: EngineSettings,
        repo_root: Path,
    ) -> AudioRunContext:
        del run_directory, settings, repo_root
        return cast(AudioRunContext, object())

    def assemble(context: AudioRunContext) -> AudioAssemblyResult:
        del context
        return _result()

    monkeypatch.setattr(assemble_script, "open_audio_run", open_run)
    monkeypatch.setattr(assemble_script, "assemble_final_audio", assemble)

    assert main(["--run", str(tmp_path)]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output == {
        "audio": "episode.mp3",
        "bytes": 512_000,
        "channels": 1,
        "codec": "mp3",
        "duration_seconds": 42.25,
        "media_type": "audio/mpeg",
        "sample_rate_hz": 48_000,
        "status": "assembled",
    }


def test_assemble_audio_cli_returns_safe_failure(
    tmp_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)

    def fail(*args: object, **kwargs: object) -> AudioRunContext:
        del args, kwargs
        raise AudioAssemblyError("FFmpeg unavailable; rerun after installation")

    monkeypatch.setattr(assemble_script, "open_audio_run", fail)

    assert main(["--run", str(tmp_path)]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "audio_assembly_failed"
    assert "rerun" in error["message"]


def test_assemble_audio_cli_rejects_missing_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    assert main(["--run", str(tmp_path)]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "invalid_settings"
