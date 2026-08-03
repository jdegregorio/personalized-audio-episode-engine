from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts"


def _json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


@pytest.mark.smoke
def test_public_validator_accepts_every_golden_artifact() -> None:
    repo_root = Path(__file__).parents[2]
    manifest = _json(FIXTURE_ROOT / "manifest.json")

    for fixture in manifest["valid"]:
        output_root_args = (
            ["--allowed-output-root", "/synthetic/run"]
            if fixture["type"] == "collection-request"
            else []
        )
        result = subprocess.run(
            [
                sys.executable,
                "scripts/validate_artifact.py",
                "--type",
                fixture["type"],
                "--input",
                str(FIXTURE_ROOT / fixture["file"]),
                *output_root_args,
            ],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (fixture, result.stderr)
        assert json.loads(result.stdout)["valid"] is True


@pytest.mark.smoke
def test_public_validator_reports_exact_path_without_mutating_input(tmp_path: Path) -> None:
    repo_root = Path(__file__).parents[2]
    data = _json(FIXTURE_ROOT / "valid" / "evidence-dossier.json")
    data["candidates"][0]["claim_ids"][0] = "claim_missing"
    input_path = tmp_path / "evidence.json"
    report_path = tmp_path / "validation-report.json"
    input_path.write_text(json.dumps(data), encoding="utf-8")
    before = hashlib.sha256(input_path.read_bytes()).hexdigest()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/validate_artifact.py",
            "--type",
            "evidence",
            "--input",
            str(input_path),
            "--report",
            str(report_path),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    concise = json.loads(result.stderr)
    issues = {(issue["code"], issue["path"]) for issue in concise["errors"]}
    assert ("unknown_claim", "/candidates/0/claim_ids/0") in issues
    full = json.loads(report_path.read_text(encoding="utf-8"))
    assert full["valid"] is False
    assert hashlib.sha256(input_path.read_bytes()).hexdigest() == before
