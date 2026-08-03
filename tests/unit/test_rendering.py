from __future__ import annotations

import wave
from pathlib import Path

import pytest

from audio_engine.rendering import TtsRenderingError, write_live_sample
from audio_engine.tts import SpeechResponse


def _pcm(seconds: float = 2.0) -> bytes:
    return b"\x00\x00" * round(24_000 * seconds)


def test_live_sample_preserves_pcm_and_writes_decodable_wave(tmp_path: Path) -> None:
    output = tmp_path / "sample.wav"

    rendered = write_live_sample(
        output,
        SpeechResponse(_pcm(), "audio/L16;codec=pcm;rate=24000"),
        expected_duration_seconds=2,
    )

    assert output.with_suffix(".pcm").read_bytes() == _pcm()
    with wave.open(str(output), "rb") as audio:
        assert audio.getparams()[:4] == (1, 2, 24_000, 48_000)
        assert audio.readframes(audio.getnframes())
    assert rendered.duration_seconds == 2.0
    assert rendered.raw_audio.sha256 != rendered.audio.sha256


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (SpeechResponse(None, None), "empty audio"),
        (SpeechResponse(b"", "audio/L16;rate=24000"), "empty audio"),
        (SpeechResponse(_pcm(), "audio/L16;rate=24000", "words"), "text instead"),
        (SpeechResponse(_pcm(), "audio/wav"), "unsupported audio media"),
        (SpeechResponse(_pcm(), "audio/L16"), "sample rate"),
        (SpeechResponse(_pcm(), "audio/L16;rate=16000"), "sample rate"),
        (SpeechResponse(b"\x00", "audio/L16;rate=24000"), "incomplete PCM"),
        (SpeechResponse(_pcm(0.2), "audio/L16;rate=24000"), "implausibly short"),
    ],
)
def test_live_sample_rejects_invalid_provider_audio(
    tmp_path: Path,
    response: SpeechResponse,
    message: str,
) -> None:
    with pytest.raises(TtsRenderingError, match=message):
        write_live_sample(
            tmp_path / "sample.wav",
            response,
            expected_duration_seconds=20,
        )


def test_invalid_raw_audio_is_preserved_before_local_validation(tmp_path: Path) -> None:
    output = tmp_path / "sample.wav"
    response = SpeechResponse(b"\x00", "audio/L16;rate=24000")

    with pytest.raises(TtsRenderingError, match="incomplete PCM"):
        write_live_sample(output, response, expected_duration_seconds=1)

    assert output.with_suffix(".pcm").read_bytes() == b"\x00"
