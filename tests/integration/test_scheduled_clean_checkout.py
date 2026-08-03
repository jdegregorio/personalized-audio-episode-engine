from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
PROTECTED_ROOTS = {
    ".agents",
    ".github",
    "docs",
    "examples",
    "schemas",
    "scripts",
    "src",
}
PROTECTED_FILES = {
    ".env.example",
    "AGENTS.md",
    "CONTRIBUTORS.md",
    "README.md",
    "plan.md",
    "prd.md",
    "pyproject.toml",
    "uv.lock",
}
SENSITIVE_ENVIRONMENT = {
    "AUDIO_ENGINE_AVAILABLE_CAPABILITIES",
    "AUDIO_ENGINE_INPUT_ROOTS",
    "AUDIO_ENGINE_MAX_RUN_AGE_SECONDS",
    "AUDIO_ENGINE_RUNTIME_ROOT",
    "AUDIO_ENGINE_STAGING_ROOT",
    "GEMINI_API_KEY",
    "PODCAST_BASE_URL",
    "PODCAST_FEED_TOKEN",
    "R2_ACCESS_KEY_ID",
    "R2_BUCKET_NAME",
    "R2_ENDPOINT_URL",
    "R2_RETENTION_DAYS",
    "R2_SECRET_ACCESS_KEY",
}


def _tracked_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(value) for value in result.stdout.split("\0") if value]


def _protected(paths: list[Path]) -> list[Path]:
    return [
        path
        for path in paths
        if path.as_posix() in PROTECTED_FILES or (path.parts and path.parts[0] in PROTECTED_ROOTS)
    ]


def _snapshot(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.as_posix(): hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths
    }


def test_offline_scheduled_fixture_leaves_clean_checkout_unchanged(tmp_path: Path) -> None:
    checkout = tmp_path / "release-candidate-checkout"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-checkout", "--no-hardlinks", str(ROOT), str(checkout)],
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "checkout", "--quiet", "--detach", candidate],
        cwd=checkout,
        check=True,
    )

    tracked = _tracked_paths(checkout)
    protected = _protected(tracked)
    before = _snapshot(checkout, protected)
    environment = {
        name: value for name, value in os.environ.items() if name not in SENSITIVE_ENVIRONMENT
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = f"{checkout / 'src'}:{checkout}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(tmp_path / "fixture-runtime"),
            "-m",
            "smoke and not live",
            "tests/smoke/test_audio_assembly_workflow.py",
        ],
        cwd=checkout,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert _snapshot(checkout, protected) == before
