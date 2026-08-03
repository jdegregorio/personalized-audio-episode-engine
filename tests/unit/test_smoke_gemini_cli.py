from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.smoke_gemini as smoke_script
from audio_engine.tts import SpeechRendererConfigurationError, SpeechResponse, TtsSegmentPrompt
from scripts.smoke_gemini import main as smoke_main

PCM = b"\x00\x00" * 24_000 * 20


class _Renderer:
    response: SpeechResponse | SpeechRendererConfigurationError = SpeechResponse(
        PCM, "audio/L16;rate=24000"
    )

    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def render(self, request: TtsSegmentPrompt) -> SpeechResponse:
        del request
        if isinstance(self.response, SpeechRendererConfigurationError):
            raise self.response
        return self.response


def test_live_smoke_cli_writes_redacted_audio_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "private-test-key")
    monkeypatch.setattr(smoke_script, "GeminiSpeechRenderer", _Renderer)
    _Renderer.response = SpeechResponse(PCM, "audio/L16;rate=24000")
    output = tmp_path / "nested" / "sample.wav"

    status = smoke_main(
        [
            "--output",
            str(output),
            "--female-voice",
            "Kore",
            "--male-voice",
            "Charon",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    metadata = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))

    assert status == 0
    assert result["result"] == "passed"
    assert result["duration_seconds"] == 20.0
    assert output.is_file()
    assert output.with_suffix(".pcm").is_file()
    assert metadata["status"] == "passed"
    assert metadata["female_voice"] == "Kore"
    assert "private-test-key" not in json.dumps(metadata)


def test_live_smoke_cli_requires_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    status = smoke_main(["--output", str(tmp_path / "sample.wav")])

    assert status == 1
    assert json.loads(capsys.readouterr().err)["code"] == "missing_gemini_api_key"


def test_live_smoke_cli_reports_safe_provider_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "private-test-key")
    monkeypatch.setattr(smoke_script, "GeminiSpeechRenderer", _Renderer)
    _Renderer.response = SpeechRendererConfigurationError("invalid voice selection")

    status = smoke_main(["--output", str(tmp_path / "sample.wav")])
    error = json.loads(capsys.readouterr().err)

    assert status == 1
    assert error == {
        "code": "gemini_live_smoke_failed",
        "message": "invalid voice selection",
        "result": "failed",
    }
