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


def test_doctor_explains_invalid_setting_without_echoing_value(
    example_profile_path: Path, settings_values: dict[str, str]
) -> None:
    invalid_url = "http://unsafe-value.invalid"
    settings_values["R2_ENDPOINT_URL"] = invalid_url

    report = run_doctor(
        example_profile_path,
        repo_root=Path(__file__).parents[2],
        environment=settings_values,
    )

    settings_check = next(check for check in report.checks if check.name == "settings")
    assert not settings_check.passed
    assert "R2_ENDPOINT_URL" in settings_check.message
    assert "HTTPS" in settings_check.message
    assert invalid_url not in settings_check.message


def test_doctor_reports_unresolvable_roots_without_traceback(
    tmp_path: Path,
    example_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.symlink_to(second)
    second.symlink_to(first)
    settings_values["AUDIO_ENGINE_RUNTIME_ROOT"] = str(first)

    report = run_doctor(
        example_profile_path,
        repo_root=Path(__file__).parents[2],
        environment=settings_values,
    )

    settings_check = next(check for check in report.checks if check.name == "settings")
    assert not settings_check.passed
    assert "roots must be resolvable" in settings_check.message


def test_doctor_reports_unresolvable_input_root_without_traceback(
    tmp_path: Path,
    example_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    first = tmp_path / "input-first"
    second = tmp_path / "input-second"
    first.symlink_to(second)
    second.symlink_to(first)
    settings_values["AUDIO_ENGINE_INPUT_ROOTS"] = str(first)

    report = run_doctor(
        example_profile_path,
        repo_root=Path(__file__).parents[2],
        environment=settings_values,
    )

    profile_check = next(check for check in report.checks if check.name == "profile")
    assert not profile_check.passed
    assert "configured root" in profile_check.message
    assert "cannot be resolved" in profile_check.message


def test_format_report_is_concise() -> None:
    report = DoctorReport((CheckResult("one", True, "ok"),))

    assert format_report(report) == "PASS one: ok\ndoctor: ready"
