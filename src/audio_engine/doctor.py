"""Non-networking environment preflight for the audio engine."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from audio_engine.config import EngineSettings
from audio_engine.profile import EpisodeProfile, ProfileError, load_profile


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    message: str


@dataclass(frozen=True)
class DoctorReport:
    checks: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failure_count(self) -> int:
        return sum(not check.passed for check in self.checks)


def _command_check(name: str, command: Sequence[str], *, cwd: Path) -> CheckResult:
    executable = shutil.which(command[0])
    if executable is None:
        return CheckResult(name, False, f"install {command[0]} and ensure it is on PATH")
    result = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return CheckResult(name, False, f"`{' '.join(command)}` failed; rerun it for details")
    return CheckResult(name, True, "available")


def _writable_directory_check(name: str, root: Path) -> CheckResult:
    try:
        resolved = root.expanduser().resolve(strict=True)
        mode = stat.S_IMODE(resolved.stat().st_mode)
    except OSError:
        return CheckResult(name, False, "create the configured absolute directory")
    if not resolved.is_dir():
        return CheckResult(name, False, "configured path must be a directory")
    if mode & 0o222 == 0 or not os.access(resolved, os.W_OK | os.X_OK):
        return CheckResult(name, False, "grant the current user write and traverse access")
    return CheckResult(name, True, "configured directory is writable")


def _settings_failure(error: ValidationError) -> CheckResult:
    details: set[str] = set()
    for item in error.errors():
        reason = str(item["msg"]).removeprefix("Value error, ")
        if item["loc"]:
            name = str(item["loc"][0])
            details.add(f"{name} ({reason})")
        else:
            details.add(reason)
    joined = "; ".join(sorted(details)) if details else "environment settings"
    return CheckResult("settings", False, f"set or correct: {joined}")


def _profile_environment_check(
    profile: EpisodeProfile,
    environment: Mapping[str, str],
) -> CheckResult:
    publishing = profile.publishing
    names = {
        publishing.private_path_env,
        publishing.endpoint_url_env,
        publishing.bucket_name_env,
        publishing.base_url_env,
        publishing.retention_days_env,
    }
    missing = sorted(name for name in names if not environment.get(name))
    if missing:
        return CheckResult("profile environment", False, f"set: {', '.join(missing)}")
    return CheckResult("profile environment", True, "publication references are present")


def _capability_check(profile: EpisodeProfile, environment: Mapping[str, str]) -> CheckResult:
    declared = {
        item.strip()
        for item in environment.get("AUDIO_ENGINE_AVAILABLE_CAPABILITIES", "").split(",")
        if item.strip()
    }
    required = set(profile.collection.required_capabilities)
    missing = sorted(required - declared)
    if missing:
        return CheckResult(
            "source capabilities",
            False,
            "make these required capabilities available: " + ", ".join(missing),
        )
    if required:
        return CheckResult("source capabilities", True, "required capabilities are declared")
    return CheckResult(
        "source capabilities",
        True,
        "none required; Codex verifies suggested/native research at collection time",
    )


def run_doctor(
    profile_path: Path,
    *,
    repo_root: Path,
    environment: Mapping[str, str] | None = None,
) -> DoctorReport:
    """Run all preflight checks without network calls, uploads, or output creation."""
    values = os.environ if environment is None else environment
    checks: list[CheckResult] = []
    version_ok = sys.version_info[:2] == (3, 12)
    checks.append(
        CheckResult(
            "python",
            version_ok,
            "Python 3.12" if version_ok else "install and run with Python 3.12",
        )
    )
    checks.extend(
        [
            _command_check("uv", ["uv", "--version"], cwd=repo_root),
            _command_check("locked dependencies", ["uv", "lock", "--check"], cwd=repo_root),
            _command_check("ffmpeg", ["ffmpeg", "-version"], cwd=repo_root),
            _command_check("ffprobe", ["ffprobe", "-version"], cwd=repo_root),
        ]
    )

    settings: EngineSettings | None = None
    try:
        settings = EngineSettings.from_mapping(values)
    except ValidationError as error:
        checks.append(_settings_failure(error))
    else:
        checks.append(CheckResult("settings", True, "required values are present and sane"))
        checks.append(_writable_directory_check("runtime root", settings.runtime_root))
        checks.append(_writable_directory_check("staging root", settings.staging_root))

    example_root = repo_root / "examples" / "profiles"
    allowed_roots = [example_root]
    if settings is not None:
        allowed_roots.extend(settings.input_roots)
    profile: EpisodeProfile | None = None
    try:
        profile = load_profile(profile_path, allowed_roots=allowed_roots)
    except (ProfileError, ValueError) as error:
        checks.append(CheckResult("profile", False, str(error)))
    else:
        checks.append(CheckResult("profile", True, "profile is valid and path-safe"))
        checks.append(_profile_environment_check(profile, values))
        checks.append(_capability_check(profile, values))

    return DoctorReport(tuple(checks))


def format_report(report: DoctorReport) -> str:
    """Render a concise one-screen report containing no configured values."""
    lines = [
        f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.message}"
        for check in report.checks
    ]
    if report.passed:
        lines.append("doctor: ready")
    else:
        lines.append(f"doctor: {report.failure_count} failure(s); fix the items above")
    return "\n".join(lines)
