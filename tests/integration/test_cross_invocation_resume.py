from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import scripts.init_run as init_run_script
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import (
    InitializationResult,
    finalize_run,
    initialize_run,
    load_run_state,
)
from audio_engine.rendering import TtsRenderingError, open_render_run, render_missing_segments
from audio_engine.storage import sha256_file
from audio_engine.tts import (
    SpeechRendererCapabilities,
    SpeechRendererError,
    SpeechResponse,
    TtsSegmentPrompt,
    renderer_capabilities,
)
from scripts.assemble_audio import main as assemble_audio_main
from scripts.prepare_tts import main as prepare_tts_main
from scripts.record_collection import main as record_collection_main
from scripts.record_editorial_plan import main as record_editorial_main
from scripts.record_script import main as record_script_main
from scripts.select_collection_method import main as select_collection_main
from tests.tts_support import configure_environment

ROOT = Path(__file__).parents[2]
ARTIFACT_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
NOW = datetime.now(UTC)
PCM = b"\x00\x00" * 24_000 * 20


class _Renderer:
    def __init__(self, *, fail_after_first: bool = False) -> None:
        self.fail_after_first = fail_after_first

    @property
    def capabilities(self) -> SpeechRendererCapabilities:
        return renderer_capabilities("gemini", "gemini-3.1-flash-tts-preview")

    def render(self, request: TtsSegmentPrompt) -> SpeechResponse:
        if self.fail_after_first and request.position > 1:
            raise SpeechRendererError("synthetic segment failure")
        return SpeechResponse(PCM, "audio/L16;codec=pcm;rate=24000")


def _copy_fixture(name: str, destination: Path) -> None:
    destination.write_bytes((ARTIFACT_ROOT / name).read_bytes())


def _build_boundary(
    boundary: str,
    *,
    profile_path: Path,
    settings: EngineSettings,
) -> Path:
    initialized = initialize_run(
        profile_path,
        settings=settings,
        repo_root=ROOT,
        clock=lambda: NOW,
        run_id_factory=lambda profile_id, day, now: f"{profile_id}_{day}_resume_boundary",
    )
    assert initialized.run_directory is not None
    run_directory = initialized.run_directory
    if boundary == "collection":
        return run_directory

    assert select_collection_main(["--run", str(run_directory)]) == 0
    _copy_fixture("evidence-dossier.json", run_directory / "evidence-dossier.json")
    assert record_collection_main(["--run", str(run_directory)]) == 0
    if boundary == "editorial":
        return run_directory

    _copy_fixture("editorial-plan.json", run_directory / "editorial-plan.json")
    assert record_editorial_main(["--run", str(run_directory)]) == 0
    if boundary == "script":
        return run_directory

    _copy_fixture("episode-script.json", run_directory / "episode-script.json")
    assert record_script_main(["--run", str(run_directory)]) == 0
    if boundary == "tts_unprepared":
        return run_directory

    assert prepare_tts_main(["--run", str(run_directory)]) == 0
    if boundary == "tts_prepared":
        return run_directory

    rendering = open_render_run(run_directory, settings=settings, repo_root=ROOT)
    if boundary == "tts_segment":
        with pytest.raises(TtsRenderingError, match="failed after"):
            render_missing_segments(
                rendering,
                _Renderer(fail_after_first=True),
                sleep=lambda delay: None,
                clock=lambda: NOW + timedelta(minutes=1),
            )
        return run_directory

    render_missing_segments(
        rendering,
        _Renderer(),
        clock=lambda: NOW + timedelta(minutes=1),
    )
    if boundary == "audio":
        return run_directory

    assert boundary == "publication"
    assert assemble_audio_main(["--run", str(run_directory)]) == 0
    return run_directory


@pytest.mark.integration
@pytest.mark.parametrize(
    "boundary",
    [
        "collection",
        "editorial",
        "script",
        "tts_unprepared",
        "tts_prepared",
        "tts_segment",
        "audio",
        "publication",
    ],
)
def test_initializer_reacquires_each_boundary_without_replacing_valid_work(
    boundary: str,
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)
    settings = EngineSettings.from_mapping(settings_values)
    run_directory = _build_boundary(
        boundary,
        profile_path=synthetic_collection_profile_path,
        settings=settings,
    )
    capsys.readouterr()
    before_state = load_run_state(run_directory / "state.json")
    before_files = {
        path.relative_to(run_directory): (sha256_file(path), path.stat().st_mtime_ns)
        for path in run_directory.rglob("*")
        if path.is_file() and path.name not in {"state.json", "summary.md"}
    }

    failed = finalize_run(
        run_directory,
        settings=settings,
        repo_root=ROOT,
        clock=lambda: datetime.now(UTC),
    )
    assert failed.status == "failed"
    failed_summary = (run_directory / "summary.md").read_text(encoding="utf-8")
    assert f"Last completed valid stage: {before_state.last_completed_valid_stage or 'none'}" in (
        failed_summary
    )
    assert "Failure:" in failed_summary
    assert "Recovery:" in failed_summary

    def fixed_initialize(profile_path: Path, **kwargs: Any) -> InitializationResult:
        return initialize_run(
            profile_path,
            **kwargs,
            clock=lambda: datetime.now(UTC),
            run_id_factory=lambda profile_id, day, now: f"{profile_id}_{day}_replacement",
        )

    monkeypatch.setattr(init_run_script, "initialize_run", fixed_initialize)
    assert init_run_script.main(["--profile", str(synthetic_collection_profile_path)]) == 0
    result = json.loads(capsys.readouterr().out)
    resumed_state = load_run_state(run_directory / "state.json")
    after_files = {
        path.relative_to(run_directory): (sha256_file(path), path.stat().st_mtime_ns)
        for path in run_directory.rglob("*")
        if path.is_file() and path.name not in {"state.json", "summary.md"}
    }

    assert result["result"] == "resumed"
    assert result["run_id"] == before_state.run_id
    assert result["run_directory"] == str(run_directory)
    assert resumed_state == before_state
    assert after_files == before_files
    assert len(list(run_directory.parent.glob("*/state.json"))) == 1
