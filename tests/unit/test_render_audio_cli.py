from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.render_audio as render_audio_script
from audio_engine.lifecycle import load_run_state
from audio_engine.tts import (
    SpeechRendererCapabilities,
    SpeechRendererConfigurationError,
    SpeechRendererError,
    SpeechResponse,
    TtsSegmentPrompt,
    renderer_capabilities,
)
from scripts.render_audio import main as render_audio_main
from tests.tts_support import SETTING_NAMES, configure_environment, ready_tts_run

PCM = b"\x00\x00" * 24_000 * 20


class _FakeGeminiRenderer:
    outcomes: list[SpeechResponse | SpeechRendererError] = []
    calls: list[str] = []

    def __init__(self, **kwargs: object) -> None:
        del kwargs

    @property
    def capabilities(self) -> SpeechRendererCapabilities:
        return renderer_capabilities("gemini", "gemini-3.1-flash-tts-preview")

    def render(self, request: TtsSegmentPrompt) -> SpeechResponse:
        self.calls.append(request.segment_id)
        outcome = (
            self.outcomes.pop(0) if self.outcomes else SpeechResponse(PCM, "audio/L16;rate=24000")
        )
        if isinstance(outcome, SpeechRendererError):
            raise outcome
        return outcome


def test_render_audio_cli_renders_and_reports_resume(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)
    run_directory = ready_tts_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()
    _FakeGeminiRenderer.calls = []
    _FakeGeminiRenderer.outcomes = []
    monkeypatch.setattr(render_audio_script, "GeminiSpeechRenderer", _FakeGeminiRenderer)

    status = render_audio_main(["--run", str(run_directory)])
    rendered = json.loads(capsys.readouterr().out)
    resumed_status = render_audio_main(["--run", str(run_directory)])
    resumed = json.loads(capsys.readouterr().out)

    assert status == 0
    assert rendered == {
        "audio_directory": "tts/audio",
        "segment_count": 2,
        "status": "rendered",
    }
    assert resumed_status == 0
    assert resumed["status"] == "already_rendered"
    assert _FakeGeminiRenderer.calls == ["tts_segment_001", "tts_segment_002"]


def test_render_audio_cli_failure_and_state_redact_api_key(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)
    run_directory = ready_tts_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()
    key = settings_values["GEMINI_API_KEY"]
    _FakeGeminiRenderer.calls = []
    _FakeGeminiRenderer.outcomes = [SpeechRendererConfigurationError(f"provider rejected {key}")]
    monkeypatch.setattr(render_audio_script, "GeminiSpeechRenderer", _FakeGeminiRenderer)

    status = render_audio_main(["--run", str(run_directory)])
    captured = capsys.readouterr()
    state_text = (run_directory / "state.json").read_text(encoding="utf-8")
    state = load_run_state(run_directory / "state.json")

    assert status == 1
    assert json.loads(captured.err)["code"] == "tts_rendering_failed"
    assert key not in captured.err
    assert key not in state_text
    assert state.tts_rendering is not None
    assert state.tts_rendering.message == "provider rejected <redacted>"


def test_render_audio_cli_rejects_missing_settings_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    status = render_audio_main(["--run", str(tmp_path)])
    error = json.loads(capsys.readouterr().err)

    assert status == 1
    assert error["code"] == "invalid_settings"
    assert "value" not in error
