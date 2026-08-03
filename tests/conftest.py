from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml


@pytest.fixture
def example_profile_path() -> Path:
    return Path(__file__).parents[1] / "examples" / "profiles" / "world-us-seattle-news.yaml"


@pytest.fixture
def example_profile_data(example_profile_path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(example_profile_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


@pytest.fixture
def settings_values(tmp_path: Path) -> dict[str, str]:
    runtime_root = tmp_path / "runtime"
    staging_root = tmp_path / "staging"
    input_root = tmp_path / "inputs"
    runtime_root.mkdir()
    staging_root.mkdir()
    input_root.mkdir()
    return {
        "GEMINI_API_KEY": "fake-gemini-key",
        "PODCAST_FEED_TOKEN": "t" * 43,
        "R2_ACCESS_KEY_ID": "fake-r2-access-key",
        "R2_SECRET_ACCESS_KEY": "fake-r2-secret-key",
        "R2_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
        "R2_BUCKET_NAME": "audio-engine-test",
        "PODCAST_BASE_URL": "https://example.invalid",
        "R2_RETENTION_DAYS": "30",
        "AUDIO_ENGINE_RUNTIME_ROOT": str(runtime_root),
        "AUDIO_ENGINE_STAGING_ROOT": str(staging_root),
        "AUDIO_ENGINE_INPUT_ROOTS": str(input_root),
    }
