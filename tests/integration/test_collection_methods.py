from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from audio_engine.artifacts import CollectionMethod
from audio_engine.collection import record_collection_attempt
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import (
    RunWorkspace,
    initialize_run,
    load_run_state,
    record_collection_method,
)
from audio_engine.storage import sha256_file

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)


def _fixed_run_id(profile_id: str, episode_date: date, now: datetime) -> str:
    del now
    return f"{profile_id}_{episode_date.isoformat()}_integration"


def _dossier() -> dict[str, Any]:
    value = json.loads((FIXTURE_ROOT / "evidence-dossier.json").read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


@pytest.mark.integration
@pytest.mark.parametrize(
    "method",
    [
        CollectionMethod(type="native_research", name="Codex native web research", version=None),
        CollectionMethod(
            type="specialized_capability", name="synthetic_research_tool", version="2.1.0"
        ),
    ],
)
def test_collection_methods_use_identical_dossier_boundary_and_resume(
    method: CollectionMethod,
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings = EngineSettings.from_mapping(settings_values)
    initialized = initialize_run(
        synthetic_collection_profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
    )
    assert initialized.run_directory is not None
    workspace = RunWorkspace(
        initialized.run_directory,
        "Synthetic marine research — 2026-01-15",
        initialized.episode_key,
    )
    state = load_run_state(workspace.state_path)
    manager = LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6))
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=method,
        prompt_version="1.0.0",
    )
    dossier_path = workspace.run_directory / "evidence-dossier.json"
    dossier = _dossier()
    dossier["collection_method"] = {
        "type": "untrusted_adapter_value",
        "name": "must be replaced",
        "version": None,
    }
    dossier_path.write_text(json.dumps(dossier), encoding="utf-8")

    accepted = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    persisted_hash = sha256_file(dossier_path)
    workspace.summary_path.write_text("stale summary\n", encoding="utf-8")
    resumed = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=6),
    )
    updated = load_run_state(workspace.state_path)
    persisted = json.loads(dossier_path.read_text(encoding="utf-8"))

    assert accepted.status == "accepted"
    assert resumed.status == "already_valid"
    assert sha256_file(dossier_path) == persisted_hash
    assert updated.current_stage == "editorial"
    assert updated.collection_method == method
    assert persisted["collection_method"] == method.model_dump(mode="json")
    assert persisted["prompt_version"] == "1.0.0"
    assert "ignore previous instructions" in persisted["sources"][1]["notes"]
    assert "Current stage: editorial" in workspace.summary_path.read_text(encoding="utf-8")
