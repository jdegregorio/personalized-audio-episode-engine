"""Deterministic FFmpeg assembly and validation of final episode audio."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

from audio_engine.artifacts import (
    ArtifactReference,
    FinalAudioValidation,
    RunState,
    TtsRenderedSegment,
)
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import (
    LifecycleError,
    load_run_state,
    record_final_audio,
    record_final_audio_failure,
)
from audio_engine.rendering import (
    RenderingContext,
    open_render_run,
    verified_rendered_segments,
)
from audio_engine.safety import SafetyError, resolve_within_roots
from audio_engine.storage import (
    StorageError,
    atomic_replace_file,
    atomic_write_text,
    sha256_file,
)

_FINAL_SAMPLE_RATE_HZ = 48_000
_FINAL_CHANNELS = 1
_FFMPEG_TIMEOUT_SECONDS = 180
_FFPROBE_TIMEOUT_SECONDS = 30


class AudioAssemblyError(RuntimeError):
    """A concise, safe audio-processing or recovery failure."""


@dataclass(frozen=True)
class ProbedAudio:
    format_name: str
    codec: str
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    bytes: int


class AudioTools(Protocol):
    """The narrow technical audio-processing boundary used by assembly."""

    def probe(self, path: Path) -> ProbedAudio: ...

    def decode(self, path: Path) -> None: ...

    def encode_concat(self, concat_file: Path, output_path: Path) -> None: ...


@dataclass(frozen=True)
class FfmpegTools:
    """Bounded FFmpeg/FFprobe subprocess adapter."""

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    ffmpeg_timeout_seconds: int = _FFMPEG_TIMEOUT_SECONDS
    ffprobe_timeout_seconds: int = _FFPROBE_TIMEOUT_SECONDS

    def probe(self, path: Path) -> ProbedAudio:
        result = _run_process(
            [
                self.ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "format=format_name,duration,size:stream=codec_type,codec_name,sample_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            cwd=path.parent,
            timeout_seconds=self.ffprobe_timeout_seconds,
            operation="FFprobe inspection",
        )
        return _parse_probe(result.stdout)

    def decode(self, path: Path) -> None:
        _run_process(
            [
                self.ffmpeg_binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-xerror",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-f",
                "null",
                "-",
            ],
            cwd=path.parent,
            timeout_seconds=self.ffmpeg_timeout_seconds,
            operation="FFmpeg decode validation",
        )

    def encode_concat(self, concat_file: Path, output_path: Path) -> None:
        _run_process(
            [
                self.ffmpeg_binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-xerror",
                "-f",
                "concat",
                "-safe",
                "1",
                "-i",
                concat_file.name,
                "-vn",
                "-map_metadata",
                "-1",
                "-ac",
                str(_FINAL_CHANNELS),
                "-ar",
                str(_FINAL_SAMPLE_RATE_HZ),
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "96k",
                "-f",
                "mp3",
                str(output_path),
            ],
            cwd=concat_file.parent,
            timeout_seconds=self.ffmpeg_timeout_seconds,
            operation="FFmpeg audio assembly",
        )


@dataclass(frozen=True)
class AudioRunContext:
    rendering: RenderingContext
    state: RunState
    segments: tuple[TtsRenderedSegment, ...]


@dataclass(frozen=True)
class AudioAssemblyResult:
    status: Literal["assembled", "already_assembled"]
    validation: FinalAudioValidation

    def to_dict(self) -> dict[str, object]:
        return {
            "audio": "episode.mp3",
            "bytes": self.validation.bytes,
            "channels": self.validation.channels,
            "codec": self.validation.codec,
            "duration_seconds": self.validation.duration_seconds,
            "media_type": self.validation.media_type,
            "sample_rate_hz": self.validation.sample_rate_hz,
            "status": self.status,
        }


def open_audio_run(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
) -> AudioRunContext:
    """Open a completely rendered run and revalidate every segment."""
    rendering = open_render_run(run_directory, settings=settings, repo_root=repo_root)
    state = load_run_state(rendering.tts.workspace.state_path)
    if state.current_stage not in {"audio", "publication"}:
        raise AudioAssemblyError("audio assembly requires the audio stage")
    if state.tts_rendering is None or state.tts_rendering.status != "complete":
        raise AudioAssemblyError("audio assembly requires every TTS segment to be complete")
    segments = verified_rendered_segments(rendering, state)
    if len(segments) != len(rendering.manifest.segments):
        raise AudioAssemblyError("audio assembly requires every manifest segment in order")
    for segment in segments:
        expected = f"tts/audio/segment-{segment.order:03d}.wav"
        if segment.audio.path != expected:
            raise AudioAssemblyError("rendered audio path does not match manifest order")
    return AudioRunContext(rendering, state, segments)


def assemble_final_audio(
    context: AudioRunContext,
    *,
    tools: AudioTools | None = None,
) -> AudioAssemblyResult:
    """Assemble validated WAVs and only then atomically record the final MP3."""
    selected_tools = tools or FfmpegTools()
    workspace = context.rendering.tts.workspace
    final_path = workspace.run_directory / "episode.mp3"
    expected_duration = sum(segment.duration_seconds for segment in context.segments)

    if context.state.current_stage == "publication":
        try:
            validation = _revalidate_recorded_final(
                context.state,
                final_path,
                expected_duration=expected_duration,
                tools=selected_tools,
            )
        except AudioAssemblyError as error:
            raise _recorded_assembly_failure(context, error) from error
        return AudioAssemblyResult("already_assembled", validation)

    concat_path: Path | None = None
    temporary_output: Path | None = None
    try:
        audio_paths = _validate_segments(context, selected_tools)
        concat_path = _write_concat_file(audio_paths)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=workspace.run_directory,
            prefix=".episode.mp3.",
            suffix=".tmp",
        )
        os.close(descriptor)
        temporary_output = Path(temporary_name)
        selected_tools.encode_concat(concat_path, temporary_output)
        probe = selected_tools.probe(temporary_output)
        selected_tools.decode(temporary_output)
        validation = _valid_final_audio(
            temporary_output,
            probe,
            expected_duration=expected_duration,
        )
        atomic_replace_file(temporary_output, final_path)
        temporary_output = None
        validation = validation.model_copy(
            update={
                "artifact": ArtifactReference(
                    artifact_type="audio",
                    path="episode.mp3",
                    sha256=sha256_file(final_path),
                )
            }
        )
    except (AudioAssemblyError, OSError, SafetyError, StorageError) as error:
        raise _recorded_assembly_failure(context, error) from error
    finally:
        for path in (concat_path, temporary_output):
            if path is not None:
                with suppress(OSError):
                    path.unlink(missing_ok=True)

    try:
        record_final_audio(
            workspace,
            context.rendering.tts.manager,
            context.rendering.tts.run_id,
            validation=validation,
        )
    except LifecycleError as error:
        raise AudioAssemblyError(
            "validated final audio could not be recorded; rerun assemble_audio.py"
        ) from error
    return AudioAssemblyResult("assembled", validation)


def _recorded_assembly_failure(
    context: AudioRunContext,
    error: Exception,
) -> AudioAssemblyError:
    message = (
        f"Audio assembly failed: {error}. Verify FFmpeg/FFprobe and the recorded segment "
        "files, then rerun assemble_audio.py; rendered segments are preserved."
    )
    try:
        record_final_audio_failure(
            context.rendering.tts.workspace,
            context.rendering.tts.manager,
            context.rendering.tts.run_id,
            message=message,
        )
    except LifecycleError:
        return AudioAssemblyError("audio assembly failed and recovery state could not be recorded")
    return AudioAssemblyError(message)


def _validate_segments(context: AudioRunContext, tools: AudioTools) -> tuple[Path, ...]:
    result: list[Path] = []
    workspace = context.rendering.tts.workspace
    for segment in context.segments:
        path = resolve_within_roots(
            workspace.run_directory / segment.audio.path,
            [workspace.run_directory],
            must_exist=True,
        )
        if sha256_file(path) != segment.audio.sha256:
            raise AudioAssemblyError("one rendered WAV hash no longer matches its state")
        probe = tools.probe(path)
        if (
            "wav" not in probe.format_name.split(",")
            or probe.codec != "pcm_s16le"
            or probe.sample_rate_hz != segment.sample_rate_hz
            or probe.channels != segment.channels
            or probe.bytes != path.stat().st_size
            or abs(probe.duration_seconds - segment.duration_seconds)
            > max(0.05, segment.duration_seconds * 0.001)
        ):
            raise AudioAssemblyError("one rendered WAV failed format or duration validation")
        tools.decode(path)
        result.append(path)
    return tuple(result)


def _write_concat_file(audio_paths: tuple[Path, ...]) -> Path:
    if not audio_paths:
        raise AudioAssemblyError("audio assembly received no segments")
    parent = audio_paths[0].parent
    if any(path.parent != parent for path in audio_paths):
        raise AudioAssemblyError("rendered WAV files do not share the canonical audio directory")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent,
        prefix=".segments-",
        suffix=".txt",
    )
    os.close(descriptor)
    path = Path(temporary_name)
    try:
        atomic_write_text(path, "".join(f"file '{audio.name}'\n" for audio in audio_paths))
    except StorageError:
        with suppress(OSError):
            path.unlink(missing_ok=True)
        raise
    return path


def _revalidate_recorded_final(
    state: RunState,
    final_path: Path,
    *,
    expected_duration: float,
    tools: AudioTools,
) -> FinalAudioValidation:
    recorded = state.final_audio_validation
    if recorded.status != "valid" or recorded.artifact is None:
        raise AudioAssemblyError("publication stage has no valid final audio state")
    try:
        if sha256_file(final_path) != recorded.artifact.sha256:
            raise AudioAssemblyError("recorded final audio hash no longer matches its file")
        probe = tools.probe(final_path)
        tools.decode(final_path)
        current = _valid_final_audio(final_path, probe, expected_duration=expected_duration)
    except (OSError, StorageError) as error:
        raise AudioAssemblyError("recorded final audio is missing or unreadable") from error
    comparable = current.model_copy(update={"artifact": recorded.artifact})
    if comparable != recorded:
        raise AudioAssemblyError("recorded final audio metadata no longer matches its file")
    return recorded


def _valid_final_audio(
    path: Path,
    probe: ProbedAudio,
    *,
    expected_duration: float,
) -> FinalAudioValidation:
    tolerance = max(0.5, expected_duration * 0.02)
    if (
        "mp3" not in probe.format_name.split(",")
        or probe.codec != "mp3"
        or probe.sample_rate_hz != _FINAL_SAMPLE_RATE_HZ
        or probe.channels != _FINAL_CHANNELS
        or probe.bytes != path.stat().st_size
        or probe.bytes < 1
        or abs(probe.duration_seconds - expected_duration) > tolerance
    ):
        raise AudioAssemblyError("final MP3 failed codec, format, size, or duration validation")
    return FinalAudioValidation(
        status="valid",
        artifact=ArtifactReference(
            artifact_type="audio",
            path="episode.mp3",
            sha256=sha256_file(path),
        ),
        media_type="audio/mpeg",
        codec="mp3",
        duration_seconds=probe.duration_seconds,
        sample_rate_hz=probe.sample_rate_hz,
        channels=probe.channels,
        bytes=probe.bytes,
        decode_status="passed",
        message="Final MP3 passed format, duration, size, and full-decode validation.",
    )


def _run_process(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    operation: str,
) -> subprocess.CompletedProcess[str]:
    if timeout_seconds < 1:
        raise AudioAssemblyError(f"{operation} timeout configuration is invalid")
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise AudioAssemblyError(
            f"{operation} timed out after {timeout_seconds} seconds"
        ) from error
    except OSError as error:
        raise AudioAssemblyError(f"{operation} executable is unavailable") from error
    if result.returncode != 0:
        raise AudioAssemblyError(f"{operation} failed")
    return result


def _parse_probe(output: str) -> ProbedAudio:
    try:
        raw_payload = cast(object, json.loads(output))
        if not isinstance(raw_payload, dict):
            raise TypeError
        payload = cast(dict[str, object], raw_payload)
        raw_streams = payload.get("streams")
        raw_format = payload.get("format")
        if not isinstance(raw_streams, list) or not isinstance(raw_format, dict):
            raise TypeError
        streams = [
            cast(dict[str, object], item)
            for item in cast(list[object], raw_streams)
            if isinstance(item, dict)
        ]
        if len(streams) != 1 or streams[0].get("codec_type") != "audio":
            raise ValueError
        stream = streams[0]
        audio_format = cast(dict[str, object], raw_format)
        return ProbedAudio(
            format_name=str(audio_format["format_name"]),
            codec=str(stream["codec_name"]),
            duration_seconds=float(cast(str | int | float, audio_format["duration"])),
            sample_rate_hz=int(cast(str | int, stream["sample_rate"])),
            channels=int(cast(str | int, stream["channels"])),
            bytes=int(cast(str | int, audio_format["size"])),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AudioAssemblyError("FFprobe returned invalid audio metadata") from error
