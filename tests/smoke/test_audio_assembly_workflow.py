from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path

import pytest

import scripts.render_audio as render_audio_script
from audio_engine.audio import FfmpegTools
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import initialize_run, load_run_state
from audio_engine.publication import (
    MemoryObjectStore,
    PreconditionFailed,
    PublicationError,
    publish_episode,
    validate_rss,
)
from audio_engine.storage import sha256_bytes, sha256_file
from audio_engine.tts import (
    SpeechRendererCapabilities,
    SpeechResponse,
    TtsSegmentPrompt,
    renderer_capabilities,
)
from scripts.assemble_audio import main as assemble_audio_main
from scripts.finalize_run import main as finalize_run_main
from scripts.render_audio import main as render_audio_main
from tests.tts_support import FIXED_NOW, configure_environment, ready_tts_run

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


class _AlwaysConflictingStore(MemoryObjectStore):
    def put(self, key: str, *args: object, **kwargs: object) -> str:
        if kwargs.get("content_type") == "application/rss+xml":
            raise PreconditionFailed("synthetic feed conflict")
        return super().put(key, *args, **kwargs)  # type: ignore[arg-type]


class _UnreadableAssetStore(MemoryObjectStore):
    def verify_public(
        self,
        key: str,
        *,
        content_type: str,
        bytes: int,
        sha256: str,
    ) -> None:
        del key, content_type, bytes, sha256
        raise PublicationError("synthetic public asset fetch failure")


class _ExternalRaceStore(MemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self.operations: list[str] = []
        self.injected = False

    def put(self, key: str, *args: object, **kwargs: object) -> str:
        content_type = kwargs.get("content_type")
        self.operations.append(str(content_type))
        if content_type == "application/rss+xml" and not self.injected:
            self.injected = True
            body = args[0]
            assert isinstance(body, bytes)
            root = ET.fromstring(body)
            channel = root.find("channel")
            assert channel is not None
            item = channel.find("item")
            assert item is not None
            external = ET.fromstring(ET.tostring(item))
            external.find("guid").text = "external-feed:other-profile:2026-01-15"  # type: ignore[union-attr]
            external.find("title").text = "Concurrent external episode"  # type: ignore[union-attr]
            channel.append(external)
            concurrent = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            super().put(
                key,
                concurrent,
                content_type="application/rss+xml",
                cache_control="no-cache, no-store, must-revalidate",
                sha256=sha256_bytes(concurrent),
            )
            raise PreconditionFailed("synthetic external revision")
        return super().put(key, *args, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "test_layer",
    [
        pytest.param("integration", marks=pytest.mark.integration),
        pytest.param("smoke", marks=pytest.mark.smoke),
    ],
)
def test_documented_audio_and_offline_publication_create_a_resumable_podcast(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    test_layer: str,
) -> None:
    del test_layer
    configure_environment(monkeypatch, settings_values)
    run_directory = ready_tts_run(synthetic_collection_profile_path, settings_values)
    capsys.readouterr()
    monkeypatch.setattr(render_audio_script, "GeminiSpeechRenderer", _OfflineRenderer)
    assert render_audio_main(["--run", str(run_directory)]) == 0
    capsys.readouterr()

    assert assemble_audio_main(["--run", str(run_directory)]) == 0
    output = json.loads(capsys.readouterr().out)
    state = load_run_state(run_directory / "state.json")
    final_path = run_directory / "episode.mp3"
    probe = FfmpegTools().probe(final_path)
    FfmpegTools().decode(final_path)

    assert output["status"] == "assembled"
    assert output["audio"] == "episode.mp3"
    assert output["media_type"] == "audio/mpeg"
    assert probe.codec == "mp3"
    assert probe.sample_rate_hz == 48_000
    assert probe.channels == 1
    assert probe.duration_seconds == pytest.approx(40, abs=0.5)
    assert state.current_stage == "publication"
    assert state.final_audio_validation.status == "valid"

    settings = EngineSettings.from_mapping(settings_values)
    unreadable = _UnreadableAssetStore()
    with pytest.raises(PublicationError, match="assets could not be verified"):
        publish_episode(
            run_directory,
            settings=settings,
            repo_root=Path(__file__).parents[2],
            store=unreadable,
        )
    failed_state = load_run_state(run_directory / "state.json")
    assert failed_state.publication.status == "failed"
    assert failed_state.final_audio_validation.status == "valid"
    assert not any(key.startswith("feeds/") for key in unreadable.objects)

    conflicting = _AlwaysConflictingStore()
    deferred = publish_episode(
        run_directory,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        store=conflicting,
    )
    deferred_state = load_run_state(run_directory / "state.json")
    assert deferred.status == "deferred"
    assert deferred_state.publication.status == "deferred"
    assert deferred_state.final_audio_validation.status == "valid"
    assert not any(key.startswith("feeds/") for key in conflicting.objects)
    assert len(conflicting.objects) == 4

    final_audio_hash = deferred_state.artifacts["final_audio"].sha256
    final_audio_modified = final_path.stat().st_mtime_ns
    assert finalize_run_main(["--run", str(run_directory)]) == 1
    failed_finalization = json.loads(capsys.readouterr().err)
    assert failed_finalization["status"] == "failed"

    resumed = initialize_run(
        synthetic_collection_profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW + timedelta(hours=1),
        run_id_factory=lambda profile_id, day, now: f"{profile_id}_{day}_replacement",
    )
    assert resumed.result == "resumed"
    assert resumed.run_directory == run_directory
    assert load_run_state(run_directory / "state.json").artifacts["final_audio"].sha256 == (
        final_audio_hash
    )
    assert final_path.stat().st_mtime_ns == final_audio_modified

    store = _ExternalRaceStore()
    published = publish_episode(
        run_directory,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        store=store,
    )
    rerun = publish_episode(
        run_directory,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        store=store,
    )
    published_state = load_run_state(run_directory / "state.json")
    feed_objects = [value for key, value in store.objects.items() if key.startswith("feeds/")]
    assert published.status == "published"
    assert rerun.status == "already_published"
    assert published_state.publication.status == "published"
    assert published_state.last_completed_valid_stage == "publication"
    assert len(feed_objects) == 1
    assert len(store.objects) == 5
    assert feed_objects[0].content_type == "application/rss+xml"
    assert feed_objects[0].cache_control == "no-cache, no-store, must-revalidate"
    validate_rss(feed_objects[0].body)
    items = ET.fromstring(feed_objects[0].body).findall("channel/item")
    guids = [item.findtext("guid") for item in items]
    assert guids.count("marine-brief:marine-brief:2026-01-15") == 1
    assert "external-feed:other-profile:2026-01-15" in guids
    assert store.operations[:4] == [
        "audio/mpeg",
        "text/plain; charset=utf-8",
        "text/html; charset=utf-8",
        "application/json",
    ]
    assert (run_directory / "show-notes.html").is_file()
    assert (run_directory / "published-episode.json").is_file()

    assert finalize_run_main(["--run", str(run_directory)]) == 0
    finalized = json.loads(capsys.readouterr().out)
    final_state = load_run_state(run_directory / "state.json")
    summary = (run_directory / "summary.md").read_text(encoding="utf-8")
    manager = LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6))
    assert finalized["status"] == "completed"
    assert finalized["redacted_locations"] == [
        "private podcast feed",
        "published episode assets",
    ]
    assert final_state.status == "completed"
    assert final_state.current_stage == "finalized"
    assert final_state.last_completed_valid_stage == "finalized"
    assert "Overall result: completed" in summary
    assert "Valid audio created: yes" in summary
    assert "Publication succeeded: yes" in summary
    assert "Published locations: private podcast feed, published episode assets" in summary
    assert len(summary.splitlines()) <= 20
    assert not manager.lease_path(final_state.episode_key).exists()
    assert set(final_state.artifacts) == {
        "profile",
        "collection_request",
        "evidence_dossier",
        "evidence_validation",
        "editorial_plan",
        "plan_validation",
        "episode_script",
        "transcript",
        "script_validation",
        "tts_manifest",
        "final_audio",
        "show_notes",
        "published_episode",
    }
    for key, reference in final_state.artifacts.items():
        if key == "profile":
            continue
        assert sha256_file(run_directory / reference.path) == reference.sha256

    assert finalize_run_main(["--run", str(run_directory)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "already_completed"

    no_op = initialize_run(
        synthetic_collection_profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW + timedelta(hours=2),
        run_id_factory=lambda profile_id, day, now: f"{profile_id}_{day}_after_completion",
    )
    assert no_op.result == "no_op"
    assert len(list(run_directory.parent.glob("*/state.json"))) == 1
