"""Resumable speech rendering, local PCM packaging, and segment validation."""

from __future__ import annotations

import io
import random
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from audio_engine.artifacts import (
    ArtifactReference,
    RunState,
    TtsManifest,
    TtsManifestSegment,
    TtsRenderedSegment,
    TtsSegmentPrompt,
)
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import (
    LifecycleError,
    load_run_state,
    record_rendered_tts_segment,
    record_tts_render_failure,
)
from audio_engine.safety import SafetyError, resolve_within_roots
from audio_engine.storage import StorageError, atomic_write_bytes, sha256_file
from audio_engine.tts import (
    SpeechRenderer,
    SpeechRendererConfigurationError,
    SpeechRendererError,
    SpeechResponse,
    TtsRunContext,
    open_tts_run,
    prepare_tts,
)

_PCM_CHANNELS = 1
_PCM_SAMPLE_WIDTH_BYTES = 2
_RETRY_DELAYS_SECONDS = (2.0, 5.0, 12.0)


class TtsRenderingError(RuntimeError):
    """A safe rendering, validation, or resume failure."""


@dataclass(frozen=True)
class RenderingContext:
    tts: TtsRunContext
    manifest: TtsManifest
    prompts: dict[str, TtsSegmentPrompt]


@dataclass(frozen=True)
class RenderingResult:
    status: Literal["rendered", "already_rendered"]
    segment_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "audio_directory": "tts/audio",
            "segment_count": self.segment_count,
            "status": self.status,
        }


def open_render_run(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
) -> RenderingContext:
    """Open and fully revalidate one prepared TTS run."""
    tts_context = open_tts_run(run_directory, settings=settings, repo_root=repo_root)
    preparation = prepare_tts(tts_context)
    prompts: dict[str, TtsSegmentPrompt] = {}
    try:
        for segment in preparation.manifest.segments:
            path = resolve_within_roots(
                tts_context.workspace.run_directory / segment.prompt.path,
                [tts_context.workspace.run_directory],
                must_exist=True,
            )
            if sha256_file(path) != segment.prompt.sha256:
                raise TtsRenderingError("prepared TTS prompt hash no longer matches its file")
            prompt = TtsSegmentPrompt.model_validate_json(path.read_text(encoding="utf-8"))
            if prompt.segment_id != segment.segment_id:
                raise TtsRenderingError("prepared TTS prompt does not match its manifest segment")
            prompts[prompt.segment_id] = prompt
    except (OSError, UnicodeError, SafetyError, StorageError, ValidationError) as error:
        raise TtsRenderingError("prepared TTS prompt is missing or invalid") from error
    if len(prompts) != len(preparation.manifest.segments):
        raise TtsRenderingError("prepared TTS prompt IDs are not unique")
    return RenderingContext(tts_context, preparation.manifest, prompts)


def render_missing_segments(
    context: RenderingContext,
    renderer: SpeechRenderer,
    *,
    sleep: Callable[[float], None] = time.sleep,
    random_source: Callable[[], float] = random.random,
    clock: Callable[[], datetime] | None = None,
    sensitive_values: tuple[str, ...] = (),
) -> RenderingResult:
    """Render missing segments in order and persist each success immediately."""
    if renderer.capabilities.provider != context.manifest.provider or (
        renderer.capabilities.model != context.manifest.model
    ):
        raise TtsRenderingError("speech renderer does not match the prepared provider and model")
    now = clock or (lambda: datetime.now(UTC))
    state = load_run_state(context.tts.workspace.state_path)
    completed = _verified_completed_segments(context, state)
    if state.current_stage == "audio":
        if state.tts_rendering is None or state.tts_rendering.status != "complete":
            raise TtsRenderingError("audio stage is missing complete TTS rendering state")
        return RenderingResult("already_rendered", len(context.manifest.segments))
    if state.current_stage != "tts":
        raise TtsRenderingError("audio rendering can only run during the TTS stage")

    maximum_retries = min(context.tts.profile.tts.maximum_retries, len(_RETRY_DELAYS_SECONDS))
    for segment in context.manifest.segments:
        if segment.segment_id in completed:
            continue
        prompt = context.prompts[segment.segment_id]
        last_error: RuntimeError | None = None
        attempts = maximum_retries + 1
        attempt = 0
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                sleep(_jittered_delay(_RETRY_DELAYS_SECONDS[attempt - 2], random_source()))
            try:
                response = renderer.render(prompt)
                rendered = _persist_valid_response(
                    context,
                    segment,
                    response,
                    request_attempts=attempt,
                    completed_at=_aware_utc(now()),
                )
                state = record_rendered_tts_segment(
                    context.tts.workspace,
                    context.tts.manager,
                    context.tts.run_id,
                    manifest=context.manifest,
                    manifest_segment=segment,
                    rendered=rendered,
                )
                completed[segment.segment_id] = rendered
                break
            except SpeechRendererConfigurationError as error:
                last_error = error
                break
            except LifecycleError as error:
                raise TtsRenderingError(
                    "validated TTS audio could not be recorded; rerun from this segment"
                ) from error
            except (SpeechRendererError, TtsRenderingError) as error:
                last_error = error
        if segment.segment_id not in completed:
            safe_message = str(last_error or "segment rendering failed")
            guidance = (
                f"Correct the provider or response issue, then rerun render_audio.py; "
                f"completed segments are preserved and rendering resumes at {segment.segment_id}."
            )
            try:
                record_tts_render_failure(
                    context.tts.workspace,
                    context.tts.manager,
                    context.tts.run_id,
                    manifest=context.manifest,
                    segment_id=segment.segment_id,
                    message=safe_message,
                    recovery_guidance=guidance,
                    sensitive_values=sensitive_values,
                )
            except LifecycleError as error:
                raise TtsRenderingError(str(error)) from error
            raise TtsRenderingError(
                f"{segment.segment_id} failed after {attempt} request attempt(s); {guidance}"
            ) from last_error

    if state.current_stage != "audio":
        raise TtsRenderingError("rendering completed without advancing to the audio stage")
    return RenderingResult("rendered", len(context.manifest.segments))


def verified_rendered_segments(
    context: RenderingContext,
    state: RunState,
) -> tuple[TtsRenderedSegment, ...]:
    """Return the manifest-ordered, hash-checked rendered segment prefix."""
    completed = _verified_completed_segments(context, state)
    return tuple(
        completed[segment.segment_id]
        for segment in context.manifest.segments
        if segment.segment_id in completed
    )


def write_live_sample(
    output_path: Path,
    response: SpeechResponse,
    *,
    expected_duration_seconds: int,
) -> TtsRenderedSegment:
    """Persist and validate one standalone live-smoke response."""
    output_path = output_path.resolve()
    raw_path = output_path.with_suffix(".pcm")
    prompt_reference = ArtifactReference(
        artifact_type="tts-prompt",
        path="live-smoke-prompt.json",
        sha256="sha256:" + "0" * 64,
    )
    segment = TtsManifestSegment(
        segment_id="tts_live_smoke",
        order=1,
        prompt=prompt_reference,
        turn_ids=["turn_live_smoke"],
        planned_segment_ids=[],
        estimated_duration_seconds=expected_duration_seconds,
        estimated_input_tokens=1,
    )
    return _persist_pcm_response(
        response,
        segment=segment,
        raw_path=raw_path,
        audio_path=output_path,
        raw_reference_path=raw_path.name,
        audio_reference_path=output_path.name,
        request_attempts=1,
        completed_at=datetime.now(UTC),
    )


def _persist_valid_response(
    context: RenderingContext,
    segment: TtsManifestSegment,
    response: SpeechResponse,
    *,
    request_attempts: int,
    completed_at: datetime,
) -> TtsRenderedSegment:
    audio_directory = context.tts.workspace.run_directory / "tts" / "audio"
    try:
        audio_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        resolved = resolve_within_roots(
            audio_directory, [context.tts.workspace.run_directory], must_exist=True
        )
    except (OSError, SafetyError) as error:
        raise TtsRenderingError("TTS audio directory is unavailable") from error
    basename = f"segment-{segment.order:03d}"
    return _persist_pcm_response(
        response,
        segment=segment,
        raw_path=resolved / f"{basename}.pcm",
        audio_path=resolved / f"{basename}.wav",
        raw_reference_path=f"tts/audio/{basename}.pcm",
        audio_reference_path=f"tts/audio/{basename}.wav",
        request_attempts=request_attempts,
        completed_at=completed_at,
    )


def _persist_pcm_response(
    response: SpeechResponse,
    *,
    segment: TtsManifestSegment,
    raw_path: Path,
    audio_path: Path,
    raw_reference_path: str,
    audio_reference_path: str,
    request_attempts: int,
    completed_at: datetime,
) -> TtsRenderedSegment:
    if response.text:
        raise TtsRenderingError("speech provider returned text instead of audio")
    if not response.audio:
        raise TtsRenderingError("speech provider returned empty audio")
    if not response.mime_type:
        raise TtsRenderingError("speech provider returned audio without a media type")
    sample_rate = _pcm_sample_rate(response.mime_type)
    try:
        atomic_write_bytes(raw_path, response.audio)
    except StorageError as error:
        raise TtsRenderingError("raw provider audio could not be preserved") from error
    if len(response.audio) % (_PCM_CHANNELS * _PCM_SAMPLE_WIDTH_BYTES):
        raise TtsRenderingError("raw provider audio has an incomplete PCM frame")
    frames = len(response.audio) // (_PCM_CHANNELS * _PCM_SAMPLE_WIDTH_BYTES)
    duration = frames / sample_rate
    minimum_duration = max(1.0, min(15.0, segment.estimated_duration_seconds * 0.1))
    if duration < minimum_duration:
        raise TtsRenderingError("speech provider audio duration is implausibly short")
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as output:
        output.setnchannels(_PCM_CHANNELS)
        output.setsampwidth(_PCM_SAMPLE_WIDTH_BYTES)
        output.setframerate(sample_rate)
        output.writeframes(response.audio)
    try:
        atomic_write_bytes(audio_path, wav_buffer.getvalue())
        _validate_wave(audio_path, sample_rate=sample_rate, expected_frames=frames)
        return TtsRenderedSegment(
            segment_id=segment.segment_id,
            order=segment.order,
            prompt=segment.prompt,
            raw_audio=ArtifactReference(
                artifact_type="tts-raw-audio",
                path=raw_reference_path,
                sha256=sha256_file(raw_path),
            ),
            audio=ArtifactReference(
                artifact_type="tts-audio",
                path=audio_reference_path,
                sha256=sha256_file(audio_path),
            ),
            provider_media_type=response.mime_type,
            sample_rate_hz=sample_rate,
            channels=_PCM_CHANNELS,
            sample_width_bytes=_PCM_SAMPLE_WIDTH_BYTES,
            duration_seconds=duration,
            request_attempts=request_attempts,
            completed_at=completed_at,
        )
    except (OSError, StorageError, ValidationError, wave.Error) as error:
        raise TtsRenderingError("packaged segment audio is not decodable") from error


def _verified_completed_segments(
    context: RenderingContext,
    state: RunState,
) -> dict[str, TtsRenderedSegment]:
    rendering = state.tts_rendering
    if rendering is None:
        return {}
    if rendering.segment_count != len(context.manifest.segments):
        raise TtsRenderingError("rendered segment state does not match the TTS manifest")
    manifest_by_id = {segment.segment_id: segment for segment in context.manifest.segments}
    result: dict[str, TtsRenderedSegment] = {}
    try:
        for rendered in rendering.completed_segments:
            manifest_segment = manifest_by_id.get(rendered.segment_id)
            if (
                manifest_segment is None
                or rendered.order != manifest_segment.order
                or rendered.prompt != manifest_segment.prompt
            ):
                raise TtsRenderingError("rendered segment state conflicts with the manifest")
            raw_path = resolve_within_roots(
                context.tts.workspace.run_directory / rendered.raw_audio.path,
                [context.tts.workspace.run_directory],
                must_exist=True,
            )
            audio_path = resolve_within_roots(
                context.tts.workspace.run_directory / rendered.audio.path,
                [context.tts.workspace.run_directory],
                must_exist=True,
            )
            if (
                sha256_file(raw_path) != rendered.raw_audio.sha256
                or sha256_file(audio_path) != rendered.audio.sha256
            ):
                raise TtsRenderingError("completed TTS segment hash no longer matches its file")
            expected_frames = round(rendered.duration_seconds * rendered.sample_rate_hz)
            _validate_wave(
                audio_path,
                sample_rate=rendered.sample_rate_hz,
                expected_frames=expected_frames,
            )
            result[rendered.segment_id] = rendered
    except (OSError, SafetyError, StorageError, wave.Error) as error:
        raise TtsRenderingError("completed TTS segment is missing or undecodable") from error
    return result


def _validate_wave(path: Path, *, sample_rate: int, expected_frames: int) -> None:
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getnchannels() != _PCM_CHANNELS
            or audio.getsampwidth() != _PCM_SAMPLE_WIDTH_BYTES
            or audio.getframerate() != sample_rate
            or audio.getnframes() != expected_frames
        ):
            raise TtsRenderingError("packaged segment audio metadata is invalid")
        if not audio.readframes(audio.getnframes()):
            raise TtsRenderingError("packaged segment audio is empty")


def _pcm_sample_rate(mime_type: str) -> int:
    parts = [part.strip() for part in mime_type.split(";")]
    if parts[0].lower() != "audio/l16":
        raise TtsRenderingError("speech provider returned an unsupported audio media type")
    parameters: dict[str, str] = {}
    for part in parts[1:]:
        key, separator, value = part.partition("=")
        if separator:
            parameters[key.strip().lower()] = value.strip().lower()
    if parameters.get("codec", "pcm") != "pcm":
        raise TtsRenderingError("speech provider returned an unsupported audio codec")
    try:
        rate = int(parameters["rate"])
    except (KeyError, ValueError) as error:
        raise TtsRenderingError("speech provider PCM sample rate is missing or invalid") from error
    if rate != 24_000:
        raise TtsRenderingError("speech provider PCM sample rate is unsupported")
    return rate


def _jittered_delay(base: float, random_value: float) -> float:
    if not 0.0 <= random_value <= 1.0:
        raise TtsRenderingError("retry random source returned a value outside zero to one")
    return base * (0.8 + 0.4 * random_value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TtsRenderingError("TTS rendering timestamps must be timezone-aware")
    return value.astimezone(UTC)
