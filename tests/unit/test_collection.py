from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import audio_engine.lifecycle as lifecycle_module
from audio_engine.artifacts import CollectionMethod, CollectionRequest, EvidenceDossier, RunState
from audio_engine.collection import (
    CollectionError,
    load_collection_request,
    open_collection_run,
    record_collection_attempt,
    select_collection_method,
)
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import (
    RunWorkspace,
    initialize_run,
    load_run_state,
    record_collection_method,
)
from audio_engine.storage import StorageError, sha256_file
from audio_engine.validation import validate_dossier_against_request

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)


def _fixed_run_id(profile_id: str, episode_date: date, now: datetime) -> str:
    del now
    return f"{profile_id}_{episode_date.isoformat()}_collection"


def _json(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _initialized(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> tuple[RunWorkspace, LeaseManager, RunState]:
    settings = EngineSettings.from_mapping(settings_values)
    result = initialize_run(
        synthetic_collection_profile_path,
        settings=settings,
        repo_root=Path(__file__).parents[2],
        clock=lambda: FIXED_NOW,
        run_id_factory=_fixed_run_id,
    )
    assert result.run_directory is not None
    workspace = RunWorkspace(
        result.run_directory,
        "Synthetic marine research — 2026-01-15",
        result.episode_key,
    )
    manager = LeaseManager(settings.runtime_root, maximum_age=timedelta(hours=6))
    return workspace, manager, load_run_state(workspace.state_path)


def _request(workspace: RunWorkspace, state: RunState) -> CollectionRequest:
    return load_collection_request(workspace, state.artifacts.get("collection_request"))


def test_collection_method_prefers_suitable_capability_and_falls_back(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, _, state = _initialized(synthetic_collection_profile_path, settings_values)
    request = _request(workspace, state)

    specialized = select_collection_method(
        request,
        {"web_deep_research": "1.2.0"},
        preferred_capability="web_deep_research",
    )
    fallback = select_collection_method(
        request,
        {"web_deep_research": "1.2.0"},
        failed_capabilities=["web_deep_research"],
    )

    assert specialized == CollectionMethod(
        type="specialized_capability",
        name="web_deep_research",
        version="1.2.0",
    )
    assert fallback.type == "native_research"
    assert fallback.version is None


def test_missing_required_capability_cannot_use_native_fallback(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, _, state = _initialized(synthetic_collection_profile_path, settings_values)
    data = _request(workspace, state).model_dump(mode="json")
    data["required_capabilities"] = ["authenticated_archive"]
    request = CollectionRequest.model_validate(data)

    with pytest.raises(CollectionError, match="authenticated_archive"):
        select_collection_method(request, {})


def test_collection_method_reports_unusable_selection_metadata(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, _, state = _initialized(synthetic_collection_profile_path, settings_values)
    request = _request(workspace, state)

    with pytest.raises(CollectionError, match="preferred.*not reported"):
        select_collection_method(request, {}, preferred_capability="missing_collector")
    with pytest.raises(CollectionError, match="metadata is invalid"):
        select_collection_method(
            request,
            {"fixture_research": "1.2.3.4"},
            preferred_capability="fixture_research",
        )

    request_data = request.model_dump(mode="json")
    request_data["allow_native_research_fallback"] = False
    without_fallback = CollectionRequest.model_validate(request_data)
    with pytest.raises(CollectionError, match="no suitable"):
        select_collection_method(without_fallback, {})


def test_one_invalid_dossier_can_be_repaired_once(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    method = CollectionMethod(
        type="native_research", name="Codex native web research", version=None
    )
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=method,
        prompt_version="1.0.0",
    )
    dossier_path = workspace.run_directory / "evidence-dossier.json"
    invalid = _json("evidence-dossier.json")
    invalid["claims"][0]["support_ids"] = []
    dossier_path.write_text(json.dumps(invalid), encoding="utf-8")

    first = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    repaired = _json("evidence-dossier.json")
    dossier_path.write_text(json.dumps(repaired), encoding="utf-8")
    second = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=6),
    )
    updated = load_run_state(workspace.state_path)

    assert first.status == "repair_required"
    assert first.attempt == 1
    assert second.status == "accepted"
    assert second.attempt == 2
    assert updated.current_stage == "editorial"
    assert updated.collection_validation is not None
    assert updated.collection_validation.status == "valid"
    assert updated.collection_validation.attempt == 2
    assert (workspace.run_directory / "evidence-validation-attempt-1.json").is_file()
    assert (workspace.run_directory / "evidence-validation-attempt-2.json").is_file()


def test_second_invalid_dossier_terminalizes_and_releases_owner(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    dossier_path = workspace.run_directory / "evidence-dossier.json"
    dossier_path.write_text("{}", encoding="utf-8")

    first = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    second = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=dossier_path,
        now=FIXED_NOW + timedelta(minutes=6),
    )
    failed = load_run_state(workspace.state_path)

    assert first.status == "repair_required"
    assert second.status == "failed"
    assert failed.status == "failed"
    assert failed.failure is not None
    assert failed.failure.code == "collection_validation_failed"
    assert not manager.lease_path(state.episode_key).exists()
    summary = workspace.summary_path.read_text(encoding="utf-8")
    assert "no repairs remain" in summary


def test_configured_dossier_warning_is_recorded_in_summary(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    dossier = _json("evidence-dossier.json")
    dossier["estimated_tokens"] = 50_000
    path = workspace.run_directory / "evidence-dossier.json"
    path.write_text(json.dumps(dossier), encoding="utf-8")

    result = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=path,
        now=FIXED_NOW + timedelta(minutes=5),
    )

    assert result.status == "accepted"
    assert [warning.code for warning in result.report.warnings] == ["dossier_size_warning"]
    assert "dossier valid with 1 warning" in workspace.summary_path.read_text(encoding="utf-8")


def test_configured_hard_dossier_limit_requires_repair(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    dossier = _json("evidence-dossier.json")
    dossier["estimated_tokens"] = 100_001
    path = workspace.run_directory / "evidence-dossier.json"
    path.write_text(json.dumps(dossier), encoding="utf-8")

    result = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=path,
        now=FIXED_NOW + timedelta(minutes=5),
    )

    assert result.status == "repair_required"
    assert ("dossier_limit_exceeded", "/estimated_tokens") in {
        (error.code, error.path) for error in result.report.errors
    }


def test_collection_recorder_rejects_output_outside_requested_path(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    wrong_path = workspace.run_directory / "other.json"
    wrong_path.write_text(json.dumps(_json("evidence-dossier.json")), encoding="utf-8")

    with pytest.raises(CollectionError, match="does not match"):
        record_collection_attempt(
            workspace,
            manager,
            state.run_id,
            candidate_path=wrong_path,
            now=FIXED_NOW + timedelta(minutes=5),
        )


def test_collection_recorder_reports_invalid_json_for_repair(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    path = workspace.run_directory / "evidence-dossier.json"
    path.write_text("not-json", encoding="utf-8")

    result = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=path,
        now=FIXED_NOW + timedelta(minutes=5),
    )

    assert result.status == "repair_required"
    assert [(error.code, error.path) for error in result.report.errors] == [("invalid_json", "/")]


def test_collection_recorder_rejects_tampered_request(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    (workspace.run_directory / "collection-request.json").write_text("{}", encoding="utf-8")

    with pytest.raises(CollectionError, match="no longer matches"):
        record_collection_attempt(
            workspace,
            manager,
            state.run_id,
            candidate_path=workspace.run_directory / "evidence-dossier.json",
            now=FIXED_NOW + timedelta(minutes=5),
        )


def test_collection_resume_rejects_tampered_dossier(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    path = workspace.run_directory / "evidence-dossier.json"
    path.write_text(json.dumps(_json("evidence-dossier.json")), encoding="utf-8")
    accepted = record_collection_attempt(
        workspace,
        manager,
        state.run_id,
        candidate_path=path,
        now=FIXED_NOW + timedelta(minutes=5),
    )
    assert accepted.status == "accepted"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(CollectionError, match="hash no longer matches"):
        record_collection_attempt(
            workspace,
            manager,
            state.run_id,
            candidate_path=path,
            now=FIXED_NOW + timedelta(minutes=6),
        )


def test_collection_rejects_naive_validation_timestamp(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    path = workspace.run_directory / "evidence-dossier.json"
    path.write_text(json.dumps(_json("evidence-dossier.json")), encoding="utf-8")

    with pytest.raises(CollectionError, match="timezone-aware"):
        record_collection_attempt(
            workspace,
            manager,
            state.run_id,
            candidate_path=path,
            now=datetime(2026, 1, 15, 15, 5),
        )


def test_collection_does_not_write_validation_without_lease_ownership(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    path = workspace.run_directory / "evidence-dossier.json"
    path.write_text(json.dumps(_json("evidence-dossier.json")), encoding="utf-8")
    manager.release(state.episode_key, state.run_id)

    with pytest.raises(CollectionError, match="could not be persisted"):
        record_collection_attempt(
            workspace,
            manager,
            state.run_id,
            candidate_path=path,
            now=FIXED_NOW + timedelta(minutes=5),
        )

    assert not (workspace.run_directory / "evidence-validation-attempt-1.json").exists()


def test_collection_state_write_failure_does_not_advance_to_editorial(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, manager, state = _initialized(synthetic_collection_profile_path, settings_values)
    record_collection_method(
        workspace,
        manager,
        state.run_id,
        method=CollectionMethod(
            type="native_research", name="Codex native web research", version=None
        ),
        prompt_version="1.0.0",
    )
    path = workspace.run_directory / "evidence-dossier.json"
    path.write_text(json.dumps(_json("evidence-dossier.json")), encoding="utf-8")

    def fail_state_write(workspace: RunWorkspace, state: RunState) -> None:
        del workspace, state
        raise StorageError("synthetic state failure")

    monkeypatch.setattr(lifecycle_module, "_write_run_state", fail_state_write)

    with pytest.raises(StorageError, match="synthetic state failure"):
        record_collection_attempt(
            workspace,
            manager,
            state.run_id,
            candidate_path=path,
            now=FIXED_NOW + timedelta(minutes=5),
        )

    persisted = load_run_state(workspace.state_path)
    assert persisted.current_stage == "collection"
    assert persisted.collection_validation is None
    assert "evidence_dossier" not in persisted.artifacts
    assert "evidence_validation" not in persisted.artifacts


def test_open_collection_run_rejects_unknown_workspace(
    tmp_path: Path,
    settings_values: dict[str, str],
) -> None:
    settings = EngineSettings.from_mapping(settings_values)

    with pytest.raises(CollectionError, match="run directory"):
        open_collection_run(
            tmp_path / "missing",
            settings=settings,
            repo_root=Path(__file__).parents[2],
        )


@pytest.mark.parametrize("section", [None, "unrelated"])
def test_dossier_candidate_sections_must_match_request(
    section: str | None,
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, _, state = _initialized(synthetic_collection_profile_path, settings_values)
    request = _request(workspace, state)
    data = _json("evidence-dossier.json")
    if section is None:
        data["candidates"][0]["classification"].pop("section")
    else:
        data["candidates"][0]["classification"]["section"] = section
    dossier = EvidenceDossier.model_validate(data)

    errors, _ = validate_dossier_against_request(dossier, request)

    assert len(errors) == 1
    assert errors[0].code in {"candidate_section_missing", "candidate_section_unknown"}


def test_dossier_section_targets_are_advisory_warnings(
    synthetic_collection_profile_path: Path,
    settings_values: dict[str, str],
) -> None:
    workspace, _, state = _initialized(synthetic_collection_profile_path, settings_values)
    request_data = _request(workspace, state).model_dump(mode="json")
    request_data["targets"]["by_section"]["habitat"] = 2
    request = CollectionRequest.model_validate(request_data)
    dossier = EvidenceDossier.model_validate(_json("evidence-dossier.json"))

    errors, warnings = validate_dossier_against_request(dossier, request)

    assert errors == ()
    assert [(warning.code, warning.path) for warning in warnings] == [
        ("candidate_target_shortfall", "/candidates")
    ]


def test_synthetic_dossier_hashes_match_committed_source_corpus() -> None:
    dossier = EvidenceDossier.model_validate(_json("evidence-dossier.json"))
    source_root = FIXTURE_ROOT.parents[1] / "sources" / "marine-brief"
    expected = {
        "https://sources.example.invalid/reports/reef-plot": source_root / "reef-plot.json",
        "connector://research-library/records/sensor-calibration-14": (
            source_root / "sensor-calibration-14.json"
        ),
    }

    assert {source.canonical_locator: source.content_hash for source in dossier.sources} == {
        locator: sha256_file(path) for locator, path in expected.items()
    }
