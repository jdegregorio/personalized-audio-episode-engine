from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_engine.lifecycle import load_run_state
from scripts.init_run import main as init_main
from scripts.record_collection import main as record_collection_main
from scripts.record_editorial_plan import main as record_editorial_main
from scripts.select_collection_method import main as select_main

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
_SETTING_NAMES = {
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


@pytest.mark.smoke
def test_documented_editorial_path_records_and_resumes(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in _SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name, value in settings_values.items():
        monkeypatch.setenv(name, value)

    assert init_main(["--profile", str(synthetic_collection_profile_path)]) == 0
    initialized = json.loads(capsys.readouterr().out)
    run_directory = Path(initialized["run_directory"])
    assert select_main(["--run", str(run_directory)]) == 0
    capsys.readouterr()
    dossier = json.loads((FIXTURE_ROOT / "evidence-dossier.json").read_text(encoding="utf-8"))
    (run_directory / "evidence-dossier.json").write_text(json.dumps(dossier), encoding="utf-8")
    assert record_collection_main(["--run", str(run_directory)]) == 0
    capsys.readouterr()
    plan = json.loads((FIXTURE_ROOT / "editorial-plan.json").read_text(encoding="utf-8"))
    (run_directory / "editorial-plan.json").write_text(json.dumps(plan), encoding="utf-8")

    assert record_editorial_main(["--run", str(run_directory)]) == 0
    accepted = json.loads(capsys.readouterr().out)
    assert record_editorial_main(["--run", str(run_directory)]) == 0
    resumed = json.loads(capsys.readouterr().out)
    state = load_run_state(run_directory / "state.json")

    assert accepted["status"] == "accepted"
    assert resumed["status"] == "already_valid"
    assert state.current_stage == "script"
    assert state.plan_validation is not None
    assert state.plan_validation.status == "valid"
