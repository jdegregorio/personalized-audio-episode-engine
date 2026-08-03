from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import Any, cast

import pytest

import audio_engine.collection as collection_module
from audio_engine.artifacts import ArtifactReference, CollectionMethod, CollectionRequest
from audio_engine.collection import CollectionAttemptResult, record_collection_attempt
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
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


@pytest.mark.integration
def test_concurrent_recorders_keep_report_and_state_hashes_consistent(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
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
    record_collection_method(
        workspace,
        LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6)),
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    dossier_path = workspace.run_directory / "evidence-dossier.json"
    dossier_path.write_text(json.dumps(_dossier()), encoding="utf-8")
    barrier = Barrier(2)
    original_load_request = collection_module.load_collection_request

    def synchronized_load_request(
        run_workspace: RunWorkspace,
        reference: ArtifactReference | None,
    ) -> CollectionRequest:
        request = original_load_request(run_workspace, reference)
        barrier.wait(timeout=5)
        return request

    monkeypatch.setattr(collection_module, "load_collection_request", synchronized_load_request)

    def record() -> CollectionAttemptResult | str:
        manager = LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6))
        try:
            return record_collection_attempt(
                workspace,
                manager,
                state.run_id,
                candidate_path=dossier_path,
                now=FIXED_NOW + timedelta(minutes=5),
            )
        except LifecycleError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(record)
        second = executor.submit(record)
        results = [first.result(), second.result()]

    accepted = [result for result in results if isinstance(result, CollectionAttemptResult)]
    rejected = [result for result in results if isinstance(result, str)]
    updated = load_run_state(workspace.state_path)
    assert len(accepted) == 1
    assert accepted[0].status == "accepted"
    assert rejected == ["collection validation does not allow another attempt"]
    assert updated.collection_validation is not None
    report_reference = updated.collection_validation.report
    assert sha256_file(workspace.run_directory / report_reference.path) == report_reference.sha256

    monkeypatch.setattr(collection_module, "load_collection_request", original_load_request)
    resumed = record_collection_attempt(
        workspace,
        LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6)),
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=6),
    )
    assert resumed.status == "already_valid"
