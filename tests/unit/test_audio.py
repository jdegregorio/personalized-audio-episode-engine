from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

import audio_engine.audio as audio_module
from audio_engine.artifacts import ArtifactReference, FinalAudioValidation, RunState
from audio_engine.audio import (
    AudioAssemblyError,
    FfmpegTools,
    _parse_probe,  # pyright: ignore[reportPrivateUsage]
)


def _probe_json(*, streams: int = 1) -> str:
    return json.dumps(
        {
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3",
                    "sample_rate": "48000",
                    "channels": 1,
                }
                for _ in range(streams)
            ],
            "format": {"format_name": "mp3", "duration": "12.25", "size": "2048"},
        }
    )


def test_parse_probe_returns_typed_metadata() -> None:
    result = _parse_probe(_probe_json())

    assert result.format_name == "mp3"
    assert result.codec == "mp3"
    assert result.duration_seconds == 12.25
    assert result.sample_rate_hz == 48_000
    assert result.channels == 1
    assert result.bytes == 2_048


@pytest.mark.parametrize(
    "payload",
    ["not-json", "[]", "{}", _probe_json(streams=0), _probe_json(streams=2)],
)
def test_parse_probe_rejects_invalid_or_ambiguous_metadata(payload: str) -> None:
    with pytest.raises(AudioAssemblyError, match="invalid audio metadata"):
        _parse_probe(payload)


def test_ffmpeg_wrapper_uses_bounded_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], int, Path]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, cast(int, kwargs["timeout"]), Path(str(kwargs["cwd"]))))
        output = _probe_json() if command[0] == "custom-probe" else ""
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(audio_module.subprocess, "run", run)
    tools = FfmpegTools(
        ffmpeg_binary="custom-ffmpeg",
        ffprobe_binary="custom-probe",
        ffmpeg_timeout_seconds=42,
        ffprobe_timeout_seconds=7,
    )
    input_path = tmp_path / "input.wav"
    concat = tmp_path / "segments.txt"
    output = tmp_path / "episode.tmp"

    tools.probe(input_path)
    tools.decode(input_path)
    tools.encode_concat(concat, output)

    assert [call[0][0] for call in calls] == [
        "custom-probe",
        "custom-ffmpeg",
        "custom-ffmpeg",
    ]
    assert [call[1] for call in calls] == [7, 42, 42]
    assert all(call[2] == tmp_path for call in calls)
    assert "-safe" in calls[2][0]
    assert "-xerror" in calls[1][0]
    assert "-xerror" in calls[2][0]
    assert "libmp3lame" in calls[2][0]
    assert "48000" in calls[2][0]


def test_ffmpeg_wrapper_redacts_timeout_and_process_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "secret-path-and-provider-output"

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise subprocess.TimeoutExpired(secret, 3, stderr=secret)

    monkeypatch.setattr(audio_module.subprocess, "run", timeout)

    with pytest.raises(AudioAssemblyError, match="timed out after 3") as raised:
        FfmpegTools(ffprobe_timeout_seconds=3).probe(tmp_path / secret)

    assert secret not in str(raised.value)


def test_ffmpeg_wrapper_rejects_failure_missing_executable_and_invalid_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="private path")

    monkeypatch.setattr(audio_module.subprocess, "run", failed)
    with pytest.raises(AudioAssemblyError, match="inspection failed") as failed_error:
        FfmpegTools().probe(tmp_path / "input")
    assert "private path" not in str(failed_error.value)

    def missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise FileNotFoundError

    monkeypatch.setattr(audio_module.subprocess, "run", missing)
    with pytest.raises(AudioAssemblyError, match="executable is unavailable"):
        FfmpegTools().decode(tmp_path / "input")

    with pytest.raises(AudioAssemblyError, match="timeout configuration is invalid"):
        FfmpegTools(ffprobe_timeout_seconds=0).probe(tmp_path / "input")


def _valid_final_data() -> dict[str, object]:
    return {
        "status": "valid",
        "artifact": {
            "artifact_type": "audio",
            "path": "episode.mp3",
            "sha256": "sha256:" + "a" * 64,
        },
        "media_type": "audio/mpeg",
        "codec": "mp3",
        "duration_seconds": 12.25,
        "sample_rate_hz": 48_000,
        "channels": 1,
        "bytes": 2_048,
        "decode_status": "passed",
        "message": "Final audio is valid.",
    }


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"bytes": None}, "complete validation metadata"),
        (
            {
                "artifact": ArtifactReference(
                    artifact_type="transcript",
                    path="transcript.txt",
                    sha256="sha256:" + "b" * 64,
                )
            },
            "audio artifact",
        ),
        (
            {
                "artifact": ArtifactReference(
                    artifact_type="audio",
                    path="other.mp3",
                    sha256="sha256:" + "b" * 64,
                )
            },
            "canonical episode.mp3",
        ),
        ({"sample_rate_hz": 24_000}, "mono at 44.1 or 48 kHz"),
        ({"status": "pending"}, "only valid final audio"),
    ],
)
def test_final_audio_contract_rejects_incomplete_or_noncanonical_valid_state(
    update: dict[str, object],
    message: str,
) -> None:
    data = {**_valid_final_data(), **update}

    with pytest.raises(ValidationError, match=message):
        FinalAudioValidation.model_validate(data)


def test_invalid_final_audio_requires_recovery_guidance() -> None:
    with pytest.raises(ValidationError, match="requires recovery guidance"):
        FinalAudioValidation(
            status="invalid",
            artifact=None,
            duration_seconds=None,
            message=None,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("mismatch", "match the recorded artifact"),
        ("stage", "publication stage or later"),
        ("unvalidated", "unvalidated final audio"),
    ],
)
def test_run_state_requires_final_validation_and_artifact_to_agree(
    mutation: str,
    message: str,
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid" / "run-state.json"
    data = cast(dict[str, object], json.loads(fixture.read_text(encoding="utf-8")))
    if mutation == "mismatch":
        artifacts = cast(dict[str, object], data["artifacts"])
        artifacts["final_audio"] = {
            "artifact_type": "audio",
            "path": "episode.mp3",
            "sha256": "sha256:" + "f" * 64,
        }
    elif mutation == "stage":
        data["current_stage"] = "audio"
    else:
        data["final_audio_validation"] = {
            "status": "pending",
            "artifact": None,
            "duration_seconds": None,
            "message": None,
        }

    with pytest.raises(ValidationError, match=message):
        RunState.model_validate(data)
