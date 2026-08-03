from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.finalize_run import main as finalize_run_main
from tests.tts_support import SETTING_NAMES


def test_finalize_cli_reports_invalid_settings_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    secret = "must-not-appear"
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", secret)

    status = finalize_run_main(["--run", str(tmp_path / "missing")])
    error = capsys.readouterr().err

    assert status == 1
    assert json.loads(error)["code"] == "invalid_settings"
    assert secret not in error
