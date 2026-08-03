from __future__ import annotations

import math
import subprocess
import sys
from array import array
from datetime import UTC, datetime
from pathlib import Path

import pytest

import audio_engine.audio as audio_module
from audio_engine.audio import (
    AudioAssemblyError,
    AudioRunContext,
    ProbedAudio,
    assemble_final_audio,
    open_audio_run,
)
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import load_run_state
from audio_engine.rendering import open_render_run, render_missing_segments
from audio_engine.storage import StorageError
from audio_engine.tts import (
    SpeechRendererCapabilities,
    SpeechResponse,
    TtsSegmentPrompt,
    renderer_capabilities,
)
from tests.tts_support import ready_tts_run

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 1, 15, 16, 0, tzinfo=UTC)


def _tone(frequency: int, *, seconds: int = 16, sample_rate: int = 24_000) -> bytes:
    samples = array(
        "h",
        (
            round(12_000 * math.sin(2 * math.pi * frequency * index / sample_rate))
            for index in range(sample_rate * seconds)
        ),
    )
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


TONES = (_tone(440), _tone(880))


class _ToneRenderer:
    def __init__(self) -> None:
        self.position = 0

    @property
    def capabilities(self) -> SpeechRendererCapabilities:
        return renderer_capabilities("gemini", "gemini-3.1-flash-tts-preview")

    def render(self, request: TtsSegmentPrompt) -> SpeechResponse:
        del request
        audio = TONES[self.position]
        self.position += 1
        return SpeechResponse(audio, "audio/L16;codec=pcm;rate=24000")


def _ready_audio_context(
    profile_path: Path,
    settings_values: dict[str, str],
) -> tuple[Path, AudioRunContext]:
    run_directory = ready_tts_run(profile_path, settings_values)
    settings = EngineSettings.from_mapping(settings_values)
    rendering = open_render_run(run_directory, settings=settings, repo_root=ROOT)
    render_missing_segments(rendering, _ToneRenderer(), clock=lambda: NOW)
    return run_directory, open_audio_run(run_directory, settings=settings, repo_root=ROOT)


def _zero_crossings(values: array[int]) -> int:
    return sum(
        1
        for left, right in zip(values, values[1:], strict=False)
        if (left < 0 <= right) or (left >= 0 > right)
    )


@pytest.mark.integration
def test_real_ffmpeg_assembly_preserves_order_validates_and_resumes_without_rewrite(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    tmp_path: Path,
) -> None:
    run_directory, context = _ready_audio_context(
        synthetic_collection_profile_path, settings_values
    )

    result = assemble_final_audio(context)
    state = load_run_state(run_directory / "state.json")
    final_path = run_directory / "episode.mp3"
    before = (final_path.read_bytes(), final_path.stat().st_mtime_ns)
    resumed_context = open_audio_run(
        run_directory,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=ROOT,
    )
    resumed = assemble_final_audio(resumed_context)
    after = (final_path.read_bytes(), final_path.stat().st_mtime_ns)

    decoded = tmp_path / "decoded.pcm"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(final_path),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            "48000",
            str(decoded),
        ],
        check=True,
        timeout=30,
    )
    samples = array("h")
    samples.frombytes(decoded.read_bytes())
    if sys.byteorder != "little":
        samples.byteswap()
    first = samples[4 * 48_000 : 6 * 48_000]
    second = samples[20 * 48_000 : 22 * 48_000]

    assert result.status == "assembled"
    assert resumed.status == "already_assembled"
    assert before == after
    assert state.current_stage == "publication"
    assert state.last_completed_valid_stage == "audio"
    assert state.final_audio_validation.status == "valid"
    assert state.final_audio_validation.media_type == "audio/mpeg"
    assert state.final_audio_validation.codec == "mp3"
    assert state.final_audio_validation.sample_rate_hz == 48_000
    assert state.final_audio_validation.channels == 1
    assert state.final_audio_validation.decode_status == "passed"
    assert state.artifacts["final_audio"] == state.final_audio_validation.artifact
    assert state.final_audio_validation.duration_seconds == pytest.approx(32, abs=0.5)
    assert 1_600 < _zero_crossings(first) < 1_920
    assert 3_300 < _zero_crossings(second) < 3_740
    assert "Valid audio created: yes" in (run_directory / "summary.md").read_text()


@pytest.mark.integration
@pytest.mark.parametrize("damage", ["missing", "empty", "corrupt", "tamper"])
def test_missing_empty_or_corrupt_segment_fails_without_publication_ready_audio(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    damage: str,
) -> None:
    run_directory, context = _ready_audio_context(
        synthetic_collection_profile_path, settings_values
    )
    segment_path = run_directory / context.segments[0].audio.path
    if damage == "missing":
        segment_path.unlink()
    elif damage == "empty":
        segment_path.write_bytes(b"")
    elif damage == "corrupt":
        segment_path.write_bytes(b"not a wave file")
    else:
        payload = bytearray(segment_path.read_bytes())
        payload[-1] ^= 1
        segment_path.write_bytes(payload)

    with pytest.raises(AudioAssemblyError, match="rendered segments are preserved"):
        assemble_final_audio(context)

    state = load_run_state(run_directory / "state.json")
    assert state.current_stage == "audio"
    assert state.final_audio_validation.status == "invalid"
    assert "rerun assemble_audio.py" in (state.final_audio_validation.message or "")
    assert "final_audio" not in state.artifacts
    assert not (run_directory / "episode.mp3").exists()
    assert not list(run_directory.glob(".episode.mp3.*.tmp"))
    assert not list((run_directory / "tts" / "audio").glob(".segments-*.txt"))


class _PartialTimeoutTools:
    def __init__(self, context: AudioRunContext) -> None:
        self.probes = {
            context.rendering.tts.workspace.run_directory / segment.audio.path: ProbedAudio(
                format_name="wav",
                codec="pcm_s16le",
                duration_seconds=segment.duration_seconds,
                sample_rate_hz=segment.sample_rate_hz,
                channels=segment.channels,
                bytes=(context.rendering.tts.workspace.run_directory / segment.audio.path)
                .stat()
                .st_size,
            )
            for segment in context.segments
        }

    def probe(self, path: Path) -> ProbedAudio:
        return self.probes[path]

    def decode(self, path: Path) -> None:
        del path

    def encode_concat(self, concat_file: Path, output_path: Path) -> None:
        del concat_file
        output_path.write_bytes(b"partial")
        raise AudioAssemblyError("FFmpeg audio assembly timed out after 1 second")


class _InvalidFinalTools(_PartialTimeoutTools):
    def probe(self, path: Path) -> ProbedAudio:
        if path in self.probes:
            return self.probes[path]
        return ProbedAudio(
            format_name="wav",
            codec="pcm_s16le",
            duration_seconds=32,
            sample_rate_hz=48_000,
            channels=1,
            bytes=path.stat().st_size,
        )

    def encode_concat(self, concat_file: Path, output_path: Path) -> None:
        del concat_file
        output_path.write_bytes(b"not a valid MP3")


@pytest.mark.integration
def test_timeout_cleans_partial_output_and_preserves_rendered_segments(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    run_directory, context = _ready_audio_context(
        synthetic_collection_profile_path, settings_values
    )
    segment_hashes = [segment.audio.sha256 for segment in context.segments]

    with pytest.raises(AudioAssemblyError, match="timed out"):
        assemble_final_audio(context, tools=_PartialTimeoutTools(context))

    state = load_run_state(run_directory / "state.json")
    assert state.final_audio_validation.status == "invalid"
    assert [segment.audio.sha256 for segment in context.segments] == segment_hashes
    assert not (run_directory / "episode.mp3").exists()
    assert not list(run_directory.glob(".episode.mp3.*.tmp"))


@pytest.mark.integration
def test_invalid_final_format_never_becomes_publication_ready(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    run_directory, context = _ready_audio_context(
        synthetic_collection_profile_path, settings_values
    )

    with pytest.raises(AudioAssemblyError, match="final MP3 failed"):
        assemble_final_audio(context, tools=_InvalidFinalTools(context))

    state = load_run_state(run_directory / "state.json")
    assert state.current_stage == "audio"
    assert state.final_audio_validation.status == "invalid"
    assert "final_audio" not in state.artifacts
    assert not (run_directory / "episode.mp3").exists()


@pytest.mark.integration
def test_atomic_promotion_failure_never_records_partial_mp3(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_directory, context = _ready_audio_context(
        synthetic_collection_profile_path, settings_values
    )

    def fail_promotion(source: Path, destination: Path) -> None:
        del source, destination
        raise StorageError("synthetic atomic promotion failure")

    monkeypatch.setattr(audio_module, "atomic_replace_file", fail_promotion)

    with pytest.raises(AudioAssemblyError, match="rendered segments are preserved"):
        assemble_final_audio(context)

    state = load_run_state(run_directory / "state.json")
    assert state.final_audio_validation.status == "invalid"
    assert "final_audio" not in state.artifacts
    assert not (run_directory / "episode.mp3").exists()
    assert not list(run_directory.glob(".episode.mp3.*.tmp"))


@pytest.mark.integration
def test_tampered_recorded_mp3_rolls_state_back_to_resumable_audio(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    run_directory, context = _ready_audio_context(
        synthetic_collection_profile_path, settings_values
    )
    assemble_final_audio(context)
    final_path = run_directory / "episode.mp3"
    final_path.write_bytes(final_path.read_bytes() + b"tamper")
    resumed_context = open_audio_run(
        run_directory,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=ROOT,
    )

    with pytest.raises(AudioAssemblyError, match="hash no longer matches"):
        assemble_final_audio(resumed_context)

    state = load_run_state(run_directory / "state.json")
    assert state.current_stage == "audio"
    assert state.final_audio_validation.status == "invalid"
    assert "final_audio" not in state.artifacts
