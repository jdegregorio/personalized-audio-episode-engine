from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import yaml


def _environment(settings_values: dict[str, str]) -> dict[str, str]:
    return {**os.environ, **settings_values, "AUDIO_ENGINE_MAX_RUN_AGE_SECONDS": "60"}


def _run_initializers(
    profile_paths: list[Path], environment: dict[str, str]
) -> list[dict[str, Any]]:
    repo_root = Path(__file__).parents[2]
    processes = [
        subprocess.Popen(
            [sys.executable, "scripts/init_run.py", "--profile", str(profile_path)],
            cwd=repo_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for profile_path in profile_paths
    ]
    results: list[dict[str, Any]] = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        loaded = json.loads(stdout)
        assert isinstance(loaded, dict)
        results.append(cast(dict[str, Any], loaded))
    return results


@pytest.mark.integration
def test_simultaneous_same_episode_has_one_owner_and_one_artifact_free_noop(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    results = _run_initializers(
        [synthetic_profile_path, synthetic_profile_path],
        _environment(settings_values),
    )

    assert sorted(result["result"] for result in results) == ["initialized", "no_op"]
    assert len(list(Path(settings_values["AUDIO_ENGINE_RUNTIME_ROOT"]).rglob("state.json"))) == 1
    no_op = next(result for result in results if result["result"] == "no_op")
    assert no_op["run_id"] is None
    assert no_op["run_directory"] is None


@pytest.mark.integration
def test_concurrent_stale_recoverers_converge_on_one_new_owner(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    environment = _environment(settings_values)
    first = _run_initializers([synthetic_profile_path], environment)
    assert first[0]["result"] == "initialized"
    runtime_root = Path(settings_values["AUDIO_ENGINE_RUNTIME_ROOT"])
    lease_path = next((runtime_root / "locks").glob("episode-*.json"))
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["created_at"] = "2000-01-01T00:00:00Z"
    lease["last_heartbeat_at"] = "2000-01-01T00:00:00Z"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")

    results = _run_initializers(
        [synthetic_profile_path, synthetic_profile_path],
        environment,
    )

    assert sorted(result["result"] for result in results) == ["initialized", "no_op"]
    assert len(list(runtime_root.rglob("state.json"))) == 2
    assert len(list((runtime_root / "locks").glob("episode-*.stale-*.json"))) == 1


@pytest.mark.integration
def test_different_episode_keys_initialize_concurrently(
    synthetic_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    second_data = yaml.safe_load(synthetic_profile_path.read_text(encoding="utf-8"))
    assert isinstance(second_data, dict)
    second_data["id"] = "synthetic-lifecycle-two"
    second_data["identity"]["feed_id"] = "synthetic-lifecycle-two"
    second_path = synthetic_profile_path.with_name("synthetic-lifecycle-two.yaml")
    second_path.write_text(yaml.safe_dump(second_data, sort_keys=False), encoding="utf-8")

    results = _run_initializers(
        [synthetic_profile_path, second_path],
        _environment(settings_values),
    )

    assert [result["result"] for result in results] == ["initialized", "initialized"]
    assert len({result["episode_key"] for result in results}) == 2
    assert len(list(Path(settings_values["AUDIO_ENGINE_RUNTIME_ROOT"]).rglob("state.json"))) == 2
