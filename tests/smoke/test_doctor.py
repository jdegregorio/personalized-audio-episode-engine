from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.smoke
def test_doctor_success_and_missing_settings(
    example_profile_path: Path, settings_values: dict[str, str]
) -> None:
    repo_root = Path(__file__).parents[2]
    command = [sys.executable, "scripts/doctor.py", "--profile", str(example_profile_path)]
    complete_environment = {**os.environ, **settings_values}

    success = subprocess.run(
        command,
        cwd=repo_root,
        env=complete_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0
    assert "doctor: ready" in success.stdout
    assert settings_values["PODCAST_FEED_TOKEN"] not in success.stdout

    missing_environment = {**complete_environment}
    del missing_environment["GEMINI_API_KEY"]
    failure = subprocess.run(
        command,
        cwd=repo_root,
        env=missing_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert failure.returncode != 0
    assert "GEMINI_API_KEY" in failure.stdout
    assert "doctor:" in failure.stdout
