from __future__ import annotations

import os
from pathlib import Path

from audio_engine.doctor import CheckResult, DoctorReport, format_report, run_doctor


def test_doctor_reports_missing_settings_without_values(
    example_profile_path: Path,
) -> None:
    repo_root = Path(__file__).parents[2]

    report = run_doctor(
        example_profile_path, repo_root=repo_root, environment={"PATH": os.environ["PATH"]}
    )
    output = format_report(report)

    assert not report.passed
    assert "FAIL settings: set or correct:" in output
    assert "GEMINI_API_KEY" in output
    assert "doctor:" in output


def test_doctor_rejects_non_writable_root(
    example_profile_path: Path, settings_values: dict[str, str]
) -> None:
    runtime_root = Path(settings_values["AUDIO_ENGINE_RUNTIME_ROOT"])
    runtime_root.chmod(0o555)
    try:
        repo_root = Path(__file__).parents[2]
        report = run_doctor(example_profile_path, repo_root=repo_root, environment=settings_values)
    finally:
        runtime_root.chmod(0o755)

    runtime_check = next(check for check in report.checks if check.name == "runtime root")
    assert not runtime_check.passed
    assert "write and traverse" in runtime_check.message


def test_format_report_is_concise() -> None:
    report = DoctorReport((CheckResult("one", True, "ok"),))

    assert format_report(report) == "PASS one: ok\ndoctor: ready"
