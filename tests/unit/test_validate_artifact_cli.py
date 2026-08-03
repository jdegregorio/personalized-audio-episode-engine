from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_artifact import main

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"


def test_validate_artifact_main_prints_success(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(
        [
            "--type",
            "evidence",
            "--input",
            str(FIXTURE_ROOT / "evidence-dossier.json"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["valid"] is True


def test_validate_artifact_main_writes_full_failure_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "invalid.json"
    report_path = tmp_path / "report.json"
    input_path.write_text("not json", encoding="utf-8")

    result = main(
        [
            "--type",
            "evidence",
            "--input",
            str(input_path),
            "--report",
            str(report_path),
        ]
    )

    output = json.loads(capsys.readouterr().err)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert result == 1
    assert output["errors"][0]["code"] == "invalid_json"
    assert report["errors"][0]["code"] == "invalid_json"


def test_validate_artifact_main_refuses_input_overwrite(tmp_path: Path) -> None:
    input_path = tmp_path / "artifact.json"
    input_path.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit) as captured:
        main(
            [
                "--type",
                "evidence",
                "--input",
                str(input_path),
                "--report",
                str(input_path),
            ]
        )

    assert captured.value.code == 2


def test_validate_artifact_main_reports_unwritable_report_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path = tmp_path / "missing" / "report.json"

    result = main(
        [
            "--type",
            "evidence",
            "--input",
            str(FIXTURE_ROOT / "evidence-dossier.json"),
            "--report",
            str(report_path),
        ]
    )

    output = json.loads(capsys.readouterr().err)
    assert result == 2
    assert output["errors"][0]["code"] == "report_write_failed"
