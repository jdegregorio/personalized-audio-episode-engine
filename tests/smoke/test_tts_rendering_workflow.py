from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.render_audio as render_audio_script
from audio_engine.lifecycle import load_run_state
from audio_engine.tts import (
    SpeechRendererCapabilities,
    SpeechResponse,
    TtsSegmentPrompt,
    renderer_capabilities,
)
from scripts.render_audio import main as render_audio_main
from tests.tts_support import configure_environment, ready_tts_run

PCM = b"\x00\x00" * 24_000 * 20


class _OfflineRenderer:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    @property
    def capabilities(self) -> SpeechRendererCapabilities:
        return renderer_capabilities("gemini", "gemini-3.1-flash-tts-preview")

    def render(self, request: TtsSegmentPrompt) -> SpeechResponse:
        del request
        return SpeechResponse(PCM, "audio/L16;codec=pcm;rate=24000")


@pytest.mark.smoke
def test_offline_tts_rendering_cli_creates_valid_resumable_audio(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)
    run_directory = ready_tts_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()
    monkeypatch.setattr(render_audio_script, "GeminiSpeechRenderer", _OfflineRenderer)

    assert render_audio_main(["--run", str(run_directory)]) == 0
    result = json.loads(capsys.readouterr().out)
    state = load_run_state(run_directory / "state.json")

    assert result["status"] == "rendered"
    assert state.current_stage == "audio"
    assert state.tts_rendering is not None
    assert state.tts_rendering.status == "complete"
    assert len(list((run_directory / "tts" / "audio").glob("*.pcm"))) == 2
    assert len(list((run_directory / "tts" / "audio").glob("*.wav"))) == 2
