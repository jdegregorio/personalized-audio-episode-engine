from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from audio_engine.lifecycle import load_run_state
from audio_engine.validation import load_artifact_file


@pytest.mark.smoke
def test_init_run_public_command_creates_inspectable_run_and_concurrent_noop(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    repo_root = Path(__file__).parents[2]
    environment = {**os.environ, **settings_values}
    command = [sys.executable, "scripts/init_run.py", "--profile", str(synthetic_profile_path)]
    processes = [
        subprocess.Popen(
            command,
            cwd=repo_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs: list[dict[str, Any]] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        value = json.loads(stdout)
        assert isinstance(value, dict)
        outputs.append(cast(dict[str, Any], value))

    assert sorted(output["result"] for output in outputs) == ["initialized", "no_op"]
    owner = next(output for output in outputs if output["result"] == "initialized")
    run_directory = Path(owner["run_directory"])
    state = load_run_state(run_directory / "state.json")
    request, report = load_artifact_file(
        "collection-request",
        run_directory / "collection-request.json",
        allowed_output_roots=[run_directory],
    )
    summary = (run_directory / "summary.md").read_text(encoding="utf-8")

    assert report.valid and request is not None
    assert state.run_id == owner["run_id"]
    assert state.current_stage == "collection"
    assert "Overall result: running" in summary
    assert "Last completed valid stage: initialized" in summary
    assert len(list(Path(settings_values["AUDIO_ENGINE_RUNTIME_ROOT"]).rglob("state.json"))) == 1
