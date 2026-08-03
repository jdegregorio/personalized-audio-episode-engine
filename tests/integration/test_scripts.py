from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from audio_engine.artifacts import EditorialPlan, EpisodeScript, EvidenceDossier
from audio_engine.profile import load_profile
from audio_engine.validation import (
    validate_artifact_data,
    validate_script_against_plan_and_dossier,
    validate_script_against_profile,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures"
ARTIFACT_ROOT = FIXTURE_ROOT / "artifacts" / "valid"
CASES = cast(
    list[dict[str, Any]],
    json.loads((FIXTURE_ROOT / "scripts" / "golden-cases.json").read_text(encoding="utf-8")),
)


@pytest.mark.integration
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_script_golden_cases(case: dict[str, Any]) -> None:
    script_data = copy.deepcopy(_load_json(ARTIFACT_ROOT / "episode-script.json"))
    first_turn = cast(dict[str, Any], cast(list[object], script_data["turns"])[0])
    first_turn["text"] = cast(str, first_turn["text"]) + cast(str, case.get("append_text", ""))
    if repeat_count := cast(int, case.get("repeat_count", 0)):
        repeat_word = cast(str, case["repeat_word"])
        first_turn["text"] += " " + " ".join([repeat_word] * repeat_count)

    script, script_report = validate_artifact_data("script", script_data)
    dossier, dossier_report = validate_artifact_data(
        "evidence", _load_json(ARTIFACT_ROOT / "evidence-dossier.json")
    )
    plan, plan_report = validate_artifact_data(
        "plan", _load_json(FIXTURE_ROOT / cast(str, case["plan"]))
    )
    assert isinstance(script, EpisodeScript), script_report.errors
    assert isinstance(dossier, EvidenceDossier), dossier_report.errors
    assert isinstance(plan, EditorialPlan), plan_report.errors

    profile_path = (
        Path(__file__).parents[2] / "examples" / "profiles" / "synthetic-marine-brief.yaml"
    )
    profile = load_profile(profile_path, allowed_roots=[profile_path.parent])
    lineage_errors = validate_script_against_plan_and_dossier(script, plan, dossier)
    profile_errors, profile_warnings = validate_script_against_profile(script, plan, profile)

    assert {issue.code for issue in (*lineage_errors, *profile_errors)} == set(
        case["expected_errors"]
    )
    assert {issue.code for issue in profile_warnings} == set(case["expected_warnings"])


def _load_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)
