from __future__ import annotations

from pathlib import Path

from scripts.check_artifacts import artifact_contract_errors


def test_repository_artifact_contracts_are_current() -> None:
    repo_root = Path(__file__).parents[2]

    assert artifact_contract_errors(repo_root) == []
