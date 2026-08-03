from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import yaml

from audio_engine.artifacts import EditorialPlan, EvidenceDossier
from audio_engine.profile import EpisodeProfile, validate_profile_data
from audio_engine.validation import (
    validate_artifact_data,
    validate_plan_against_dossier,
    validate_plan_against_profile,
)

ARTIFACT_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"
PLAN_ROOT = Path(__file__).parents[1] / "fixtures" / "editorial-plans"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _profile_data(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _models(plan_path: Path) -> tuple[EditorialPlan, EvidenceDossier]:
    plan, plan_report = validate_artifact_data("plan", _json(plan_path))
    dossier, dossier_report = validate_artifact_data(
        "evidence", _json(ARTIFACT_ROOT / "evidence-dossier.json")
    )
    assert plan_report.valid and isinstance(plan, EditorialPlan)
    assert dossier_report.valid and isinstance(dossier, EvidenceDossier)
    return plan, dossier


def _validate(
    plan: EditorialPlan,
    dossier: EvidenceDossier,
    profile: EpisodeProfile,
) -> tuple[set[str], set[str]]:
    errors = {
        issue.code
        for issue in (
            *validate_plan_against_dossier(plan, dossier),
            *validate_plan_against_profile(plan, dossier, profile)[0],
        )
    }
    warnings = {issue.code for issue in validate_plan_against_profile(plan, dossier, profile)[1]}
    return errors, warnings


def test_ordinary_and_shorter_golden_plans_are_valid(
    synthetic_collection_profile_path: Path,
) -> None:
    profile = validate_profile_data(_profile_data(synthetic_collection_profile_path))
    ordinary, dossier = _models(ARTIFACT_ROOT / "editorial-plan.json")
    shorter, _ = _models(PLAN_ROOT / "shorter-useful.json")

    assert _validate(ordinary, dossier, profile) == (set(), set())
    assert _validate(shorter, dossier, profile) == (set(), {"section_target_shortfall"})


def test_optional_empty_section_golden_plan_avoids_filler(
    synthetic_collection_profile_path: Path,
) -> None:
    profile_data = _profile_data(synthetic_collection_profile_path)
    profile_data["editorial"]["allow_empty_sections"] = ["methods"]
    profile = validate_profile_data(profile_data)
    plan, dossier = _models(PLAN_ROOT / "optional-empty-section.json")

    assert _validate(plan, dossier, profile) == (set(), set())


def test_source_disagreement_requires_and_accepts_a_plan_note(
    synthetic_collection_profile_path: Path,
) -> None:
    profile = validate_profile_data(_profile_data(synthetic_collection_profile_path))
    plan, dossier = _models(PLAN_ROOT / "source-disagreement.json")
    dossier_data = dossier.model_dump(mode="json")
    dossier_data["candidates"][0]["source_differences"]["meaningful_differences"] = [
        "The long-term interpretation differs."
    ]
    disputed, report = validate_artifact_data("evidence", dossier_data)
    assert report.valid and isinstance(disputed, EvidenceDossier)

    assert _validate(plan, disputed, profile) == (set(), set())

    plan_data = plan.model_dump(mode="json")
    plan_data["segments"][0]["source_conflict_notes"] = []
    without_note, report = validate_artifact_data("plan", plan_data)
    assert report.valid and isinstance(without_note, EditorialPlan)
    assert "missing_source_conflict_notes" in _validate(without_note, disputed, profile)[0]


def test_arbitrary_non_news_taxonomy_uses_only_profile_data(
    synthetic_collection_profile_path: Path,
) -> None:
    profile_data = _profile_data(synthetic_collection_profile_path)
    profile_data["episode"]["scope"]["sections"] = [
        {"id": "observations", "description": "Field observations"},
        {"id": "instrumentation", "description": "Measurement methods"},
    ]
    profile_data["collection"]["target_candidates"] = {
        "observations": 1,
        "instrumentation": 1,
    }
    profile_data["editorial"]["target_sections"] = {
        "observations": {"minimum_items": 1, "maximum_items": 1},
        "instrumentation": {"minimum_items": 1, "maximum_items": 1},
    }
    profile_data["editorial"]["allow_empty_sections"] = []
    profile = validate_profile_data(profile_data)

    plan, dossier = _models(PLAN_ROOT / "arbitrary-taxonomy.json")
    dossier_data = dossier.model_dump(mode="json")
    dossier_data["candidates"][0]["classification"]["section"] = "observations"
    dossier_data["candidates"][1]["classification"]["section"] = "instrumentation"
    remapped, report = validate_artifact_data("evidence", dossier_data)
    assert report.valid and isinstance(remapped, EvidenceDossier)

    assert _validate(plan, remapped, profile) == (set(), set())


def test_profile_defined_exclusion_reason_is_extensible(
    synthetic_collection_profile_path: Path,
) -> None:
    profile_data = _profile_data(synthetic_collection_profile_path)
    profile_data["editorial"]["exclusion_reason_codes"] = ["field_team_priority"]
    profile = validate_profile_data(profile_data)
    plan, dossier = _models(PLAN_ROOT / "shorter-useful.json")
    plan_data = copy.deepcopy(plan.model_dump(mode="json"))
    plan_data["exclusions"][0]["reason_code"] = "field_team_priority"
    custom_plan, report = validate_artifact_data("plan", plan_data)
    assert report.valid and isinstance(custom_plan, EditorialPlan)

    assert _validate(custom_plan, dossier, profile)[0] == set()
