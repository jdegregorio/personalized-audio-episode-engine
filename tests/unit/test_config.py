from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from audio_engine.config import EngineSettings


def test_settings_load_valid_environment(settings_values: dict[str, str]) -> None:
    settings = EngineSettings.from_mapping(settings_values)

    assert settings.r2_bucket_name == "audio-engine-test"
    assert settings.r2_retention_days == 30
    assert settings.podcast_feed_token.get_secret_value() == "t" * 43
    assert settings.input_roots == (Path(settings_values["AUDIO_ENGINE_INPUT_ROOTS"]),)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PODCAST_FEED_TOKEN", "short"),
        ("GEMINI_API_KEY", ""),
        ("R2_ENDPOINT_URL", "http://example.invalid"),
        ("R2_ENDPOINT_URL", "https://example.invalid/path"),
        ("PODCAST_BASE_URL", "https://example.invalid?token=unsafe"),
        ("R2_BUCKET_NAME", "Not_A_Bucket"),
        ("R2_RETENTION_DAYS", "0"),
        ("AUDIO_ENGINE_RUNTIME_ROOT", "relative/runtime"),
    ],
)
def test_settings_reject_unsafe_values(
    settings_values: dict[str, str], name: str, value: str
) -> None:
    settings_values[name] = value

    with pytest.raises(ValidationError):
        EngineSettings.from_mapping(settings_values)


def test_settings_report_missing_values_without_reading_process_environment(
    settings_values: dict[str, str],
) -> None:
    del settings_values["GEMINI_API_KEY"]

    with pytest.raises(ValidationError) as captured:
        EngineSettings.from_mapping(settings_values)

    assert "GEMINI_API_KEY" in str(captured.value)
