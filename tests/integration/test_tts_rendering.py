from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import audio_engine.lifecycle as lifecycle_module
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import load_run_state
from audio_engine.rendering import (
    RenderingContext,
    TtsRenderingError,
    open_render_run,
    render_missing_segments,
)
from audio_engine.storage import StorageError
from audio_engine.tts import (
    SpeechRendererCapabilities,
    SpeechRendererError,
    SpeechResponse,
    TtsSegmentPrompt,
    renderer_capabilities,
)
from tests.tts_support import ready_tts_run

ROOT = Path(__file__).parents[2]
PCM = b"\x00\x00" * 24_000 * 20
NOW = datetime(2026, 1, 15, 16, 0, tzinfo=UTC)


class FakeRenderer:
    def __init__(self, outcomes: list[SpeechResponse | SpeechRendererError] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[str] = []

    @property
    def capabilities(self) -> SpeechRendererCapabilities:
        return renderer_capabilities("gemini", "gemini-3.1-flash-tts-preview")

    def render(self, request: TtsSegmentPrompt) -> SpeechResponse:
        self.calls.append(request.segment_id)
        outcome = self.outcomes.pop(0) if self.outcomes else _success()
        if isinstance(outcome, SpeechRendererError):
            raise outcome
        return outcome


def _success() -> SpeechResponse:
    return SpeechResponse(PCM, "audio/L16;codec=pcm;rate=24000")


def _context(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> tuple[Path, RenderingContext]:
    run_directory = ready_tts_run(synthetic_collection_profile_path, settings_values)
    context = open_render_run(
        run_directory,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=ROOT,
    )
    return run_directory, context


@pytest.mark.integration
def test_fake_renderer_writes_every_segment_and_idempotently_resumes(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    run_directory, context = _context(synthetic_collection_profile_path, settings_values)
    renderer = FakeRenderer()

    result = render_missing_segments(context, renderer, clock=lambda: NOW)
    state = load_run_state(run_directory / "state.json")
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted((run_directory / "tts" / "audio").iterdir())
    }
    resumed_context = open_render_run(
        run_directory,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=ROOT,
    )
    resumed_renderer = FakeRenderer()
    resumed = render_missing_segments(resumed_context, resumed_renderer)
    after = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted((run_directory / "tts" / "audio").iterdir())
    }

    assert result.status == "rendered"
    assert renderer.calls == ["tts_segment_001", "tts_segment_002"]
    assert state.current_stage == "audio"
    assert state.last_completed_valid_stage == "tts"
    assert state.tts_rendering is not None
    assert state.tts_rendering.status == "complete"
    assert len(state.tts_rendering.completed_segments) == 2
    assert all(item.duration_seconds == 20 for item in state.tts_rendering.completed_segments)
    assert resumed.status == "already_rendered"
    assert not resumed_renderer.calls
    assert before == after
    assert "TTS segments rendered: 2" in (run_directory / "summary.md").read_text()


@pytest.mark.integration
def test_transient_failure_uses_deterministic_backoff_without_repeating_prior_work(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    _, context = _context(synthetic_collection_profile_path, settings_values)
    renderer = FakeRenderer([SpeechRendererError("HTTP 500"), _success(), _success()])
    delays: list[float] = []

    render_missing_segments(
        context,
        renderer,
        sleep=delays.append,
        random_source=lambda: 0.5,
        clock=lambda: NOW,
    )

    state = load_run_state(context.tts.workspace.state_path)
    assert renderer.calls == ["tts_segment_001", "tts_segment_001", "tts_segment_002"]
    assert delays == [2.0]
    assert state.tts_rendering is not None
    assert [item.request_attempts for item in state.tts_rendering.completed_segments] == [2, 1]


@pytest.mark.integration
def test_retry_exhaustion_preserves_completed_segment_and_resumes_only_failure(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    run_directory, context = _context(synthetic_collection_profile_path, settings_values)
    failures = [SpeechRendererError("429") for _ in range(4)]
    renderer = FakeRenderer([_success(), *failures])
    delays: list[float] = []

    with pytest.raises(TtsRenderingError, match="tts_segment_002 failed after 4"):
        render_missing_segments(
            context,
            renderer,
            sleep=delays.append,
            random_source=lambda: 0.5,
            clock=lambda: NOW,
        )

    failed = load_run_state(run_directory / "state.json")
    assert failed.current_stage == "tts"
    assert failed.final_audio_validation.status == "pending"
    assert failed.tts_rendering is not None
    assert failed.tts_rendering.status == "failed"
    assert failed.tts_rendering.failed_segment_id == "tts_segment_002"
    assert len(failed.tts_rendering.completed_segments) == 1
    assert delays == [2.0, 5.0, 12.0]
    first = failed.tts_rendering.completed_segments[0]
    preserved = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (
            run_directory / first.raw_audio.path,
            run_directory / first.audio.path,
        )
    }

    resumed_context = open_render_run(
        run_directory,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=ROOT,
    )
    resumed_renderer = FakeRenderer()
    result = render_missing_segments(resumed_context, resumed_renderer, clock=lambda: NOW)
    final = load_run_state(run_directory / "state.json")

    assert result.status == "rendered"
    assert resumed_renderer.calls == ["tts_segment_002"]
    assert final.tts_rendering is not None
    assert final.tts_rendering.status == "complete"
    assert final.tts_rendering.completed_segments[0] == first
    assert preserved == {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in preserved}


@pytest.mark.integration
def test_completed_segment_tampering_fails_closed_on_resume(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    run_directory, context = _context(synthetic_collection_profile_path, settings_values)
    render_missing_segments(context, FakeRenderer(), clock=lambda: NOW)
    state = load_run_state(run_directory / "state.json")
    assert state.tts_rendering is not None
    audio = run_directory / state.tts_rendering.completed_segments[0].audio.path
    audio.write_bytes(audio.read_bytes() + b"tamper")
    resumed_context = open_render_run(
        run_directory,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=ROOT,
    )

    with pytest.raises(TtsRenderingError, match="hash no longer matches"):
        render_missing_segments(resumed_context, FakeRenderer())


@pytest.mark.integration
def test_state_write_failure_does_not_retry_a_successful_provider_response(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, context = _context(synthetic_collection_profile_path, settings_values)
    renderer = FakeRenderer()

    def fail_state_write(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise StorageError("synthetic state failure")

    monkeypatch.setattr(lifecycle_module, "_write_run_state", fail_state_write)
    with pytest.raises(TtsRenderingError, match="could not be recorded"):
        render_missing_segments(context, renderer, sleep=lambda _: None)

    assert renderer.calls == ["tts_segment_001"]


@pytest.mark.integration
def test_rendering_rejects_manifest_object_that_differs_from_persisted_artifact(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    _, context = _context(synthetic_collection_profile_path, settings_values)
    altered = RenderingContext(
        context.tts,
        context.manifest.model_copy(update={"scene_description": "different scene"}),
        context.prompts,
    )

    with pytest.raises(TtsRenderingError, match="could not be recorded"):
        render_missing_segments(altered, FakeRenderer(), sleep=lambda _: None)
