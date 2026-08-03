from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from audio_engine.lifecycle import load_run_state
from scripts.init_run import main as init_main
from scripts.prepare_tts import main as prepare_tts_main
from scripts.record_collection import main as record_collection_main
from scripts.record_editorial_plan import main as record_editorial_main
from scripts.record_script import main as record_script_main
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
@pytest.mark.parametrize("script_size", ["short", "maximum"])
def test_documented_editorial_and_script_path_records_and_resumes(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    script_size: str,
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

    script = json.loads((FIXTURE_ROOT / "episode-script.json").read_text(encoding="utf-8"))
    if script_size == "maximum":
        script = _maximum_size_script(cast(dict[str, Any], script))
    (run_directory / "episode-script.json").write_text(json.dumps(script), encoding="utf-8")
    assert record_script_main(["--run", str(run_directory)]) == 0
    script_accepted = json.loads(capsys.readouterr().out)
    assert record_script_main(["--run", str(run_directory)]) == 0
    script_resumed = json.loads(capsys.readouterr().out)
    state = load_run_state(run_directory / "state.json")

    assert script_accepted["status"] == "accepted"
    assert script_resumed["status"] == "already_valid"
    assert state.current_stage == "tts"
    assert state.script_validation is not None
    assert state.script_validation.status == "valid"
    assert state.artifacts["transcript"].path == "transcript.txt"

    assert prepare_tts_main(["--run", str(run_directory)]) == 0
    tts_prepared = json.loads(capsys.readouterr().out)
    manifest_path = run_directory / "tts" / "manifest.json"
    prompt_paths = sorted((run_directory / "tts").glob("segment-*.json"))
    before = {path: path.read_bytes() for path in [manifest_path, *prompt_paths]}
    assert prepare_tts_main(["--run", str(run_directory)]) == 0
    tts_resumed = json.loads(capsys.readouterr().out)
    after = {path: path.read_bytes() for path in [manifest_path, *prompt_paths]}
    state = load_run_state(run_directory / "state.json")

    assert tts_prepared["status"] == "prepared"
    assert tts_resumed["status"] == "already_prepared"
    assert tts_prepared["maximum_estimated_input_tokens"] <= 7000
    assert before == after
    assert state.tts_preparation is not None
    assert state.tts_preparation.segment_count == len(prompt_paths)
    assert "".join(
        json.loads(path.read_text(encoding="utf-8"))["transcript"] for path in prompt_paths
    ) == (run_directory / "transcript.txt").read_text(encoding="utf-8")


def _maximum_size_script(script: dict[str, Any]) -> dict[str, Any]:
    expanded = deepcopy(script)
    turns = cast(list[dict[str, Any]], expanded["turns"])
    template = deepcopy(turns[2])
    additions: list[dict[str, Any]] = []
    for index in range(80):
        addition = deepcopy(template)
        addition["turn_id"] = f"turn_maximum_{index:03d}"
        addition["speaker"] = "Maya" if index % 2 == 0 else "Daniel"
        addition["text"] = " ".join(["context"] * 40)
        additions.append(addition)
    expanded["turns"] = [*turns[:3], *additions, *turns[3:]]
    segments = cast(list[dict[str, Any]], expanded["segments"])
    segments[0]["turn_ids"] = [
        "turn_intro",
        "turn_reef_fact",
        "turn_reef_analysis",
        *[addition["turn_id"] for addition in additions],
    ]
    segments[0]["estimated_input_tokens"] = 6900
    expanded["estimated_duration_seconds"] = 600
    return expanded
