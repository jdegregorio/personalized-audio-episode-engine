from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from audio_engine.config import EngineSettings
from audio_engine.lifecycle import initialize_run
from scripts.prepare_tts import main as prepare_tts_main
from scripts.record_collection import main as record_collection_main
from scripts.record_editorial_plan import main as record_editorial_main
from scripts.record_script import main as record_script_main
from scripts.select_collection_method import main as select_main

FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)
ARTIFACT_ROOT = Path(__file__).parent / "fixtures" / "artifacts" / "valid"
SETTING_NAMES = {
    "GEMINI_API_KEY",
    "PODCAST_FEED_TOKEN",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "R2_BUCKET_NAME",
    "PODCAST_BASE_URL",
    "R2_RETENTION_DAYS",
    "AUDIO_ENGINE_RUNTIME_ROOT",
    "AUDIO_ENGINE_STAGING_ROOT",
    "AUDIO_ENGINE_INPUT_ROOTS",
    "AUDIO_ENGINE_MAX_RUN_AGE_SECONDS",
}


def configure_environment(
    monkeypatch: pytest.MonkeyPatch,
    settings_values: dict[str, str],
) -> None:
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in settings_values.items():
        monkeypatch.setenv(name, value)


def ready_tts_run(profile_path: Path, settings_values: dict[str, str]) -> Path:
    def run_id(profile_id: str, episode_date: date, now: datetime) -> str:
        del now
        return f"{profile_id}_{episode_date.isoformat()}_render_test"

    result = initialize_run(
        profile_path,
        settings=EngineSettings.from_mapping(settings_values),
        repo_root=Path(__file__).parents[1],
        clock=lambda: FIXED_NOW,
        run_id_factory=run_id,
    )
    assert result.run_directory is not None
    with patch.dict(os.environ, settings_values):
        assert select_main(["--run", str(result.run_directory)]) == 0
        dossier = json.loads((ARTIFACT_ROOT / "evidence-dossier.json").read_text(encoding="utf-8"))
        (result.run_directory / "evidence-dossier.json").write_text(
            json.dumps(dossier), encoding="utf-8"
        )
        assert record_collection_main(["--run", str(result.run_directory)]) == 0
        plan = json.loads((ARTIFACT_ROOT / "editorial-plan.json").read_text(encoding="utf-8"))
        (result.run_directory / "editorial-plan.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )
        assert record_editorial_main(["--run", str(result.run_directory)]) == 0
        script = json.loads((ARTIFACT_ROOT / "episode-script.json").read_text(encoding="utf-8"))
        (result.run_directory / "episode-script.json").write_text(
            json.dumps(script), encoding="utf-8"
        )
        assert record_script_main(["--run", str(result.run_directory)]) == 0
        assert prepare_tts_main(["--run", str(result.run_directory)]) == 0
    return result.run_directory
