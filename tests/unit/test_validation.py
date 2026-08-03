from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from audio_engine.artifacts import CollectionRequest
from audio_engine.validation import ARTIFACT_TYPES, ValidationReport, validate_artifact_data

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"


def _json(name: str) -> dict[str, Any]:
    loaded = json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


@pytest.mark.parametrize(
    ("artifact_type", "fixture_name"),
    [
        ("collection-request", "collection-request.json"),
        ("evidence", "evidence-dossier.json"),
        ("plan", "editorial-plan.json"),
        ("script", "episode-script.json"),
        ("published-episode", "published-episode.json"),
        ("run-state", "run-state.json"),
    ],
)
def test_all_artifacts_reject_unsupported_contract_versions(
    artifact_type: str, fixture_name: str
) -> None:
    data = _json(fixture_name)
    data["contract_version"] = "9.0"

    _, report = validate_artifact_data(artifact_type, data)

    assert not report.valid
    assert [(issue.code, issue.path) for issue in report.errors] == [
        ("unsupported_version", "/contract_version")
    ]


def test_validation_does_not_mutate_decoded_input() -> None:
    data = _json("evidence-dossier.json")
    before = copy.deepcopy(data)

    _, report = validate_artifact_data("evidence", data)

    assert report.valid
    assert data == before


def test_filesystem_locator_requires_explicit_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    source_path = allowed / "source.txt"
    source_path.write_text("synthetic source", encoding="utf-8")
    data = _json("evidence-dossier.json")
    data["sources"][0]["canonical_locator"] = str(source_path)

    _, rejected = validate_artifact_data("evidence", data)
    _, accepted = validate_artifact_data("evidence", data, allowed_input_roots=[allowed])

    assert not rejected.valid
    assert ("unsafe_locator", "/sources/0/canonical_locator") in {
        (issue.code, issue.path) for issue in rejected.errors
    }
    assert accepted.valid

    data["sources"][0]["canonical_locator"] = str(outside / "source.txt")
    _, escaped = validate_artifact_data("evidence", data, allowed_input_roots=[allowed])
    assert not escaped.valid

    data["sources"][0]["canonical_locator"] = "connector://library/records/../secret"
    _, traversed = validate_artifact_data("evidence", data)
    assert not traversed.valid

    data["sources"][0]["canonical_locator"] = "https://[malformed"
    _, malformed = validate_artifact_data("evidence", data)
    assert not malformed.valid


def test_dossier_warning_threshold_is_nonfatal() -> None:
    data = _json("evidence-dossier.json")
    data["estimated_tokens"] = 50000

    _, report = validate_artifact_data("evidence", data)

    assert report.valid
    assert [(warning.code, warning.path) for warning in report.warnings] == [
        ("dossier_size_warning", "/estimated_tokens")
    ]


def test_evidence_requires_allowed_support_type_and_consistent_source_lineage() -> None:
    invalid_type = _json("evidence-dossier.json")
    invalid_type["claim_supports"][0]["support_type"] = "corroborates"
    _, type_report = validate_artifact_data("evidence", invalid_type)
    assert not type_report.valid
    assert ("schema_error", "/claim_supports/0/support_type") in {
        (issue.code, issue.path) for issue in type_report.errors
    }

    mismatch = _json("evidence-dossier.json")
    mismatch["claim_supports"][0]["source_relationship"]["originality"] = "syndicated"
    mismatch["candidates"][0]["source_ids"] = []
    _, mismatch_report = validate_artifact_data("evidence", mismatch)
    actual = {(issue.code, issue.path) for issue in mismatch_report.errors}
    assert (
        "source_relationship_mismatch",
        "/claim_supports/0/source_relationship/originality",
    ) in actual
    assert ("candidate_source_mismatch", "/claim_supports/0/source_id") in actual


def test_only_primary_source_locator_may_replace_supporting_excerpt() -> None:
    data = _json("evidence-dossier.json")
    data["claim_supports"][0]["evidence"]["excerpt"] = None
    data["sources"][0]["is_primary"] = False
    data["sources"][0]["originality"]["kind"] = "original_reporting"
    data["claim_supports"][0]["source_relationship"]["originality"] = "original_reporting"

    _, report = validate_artifact_data("evidence", data)

    assert not report.valid
    assert ("excerpt_required", "/claim_supports/0/evidence/excerpt") in {
        (issue.code, issue.path) for issue in report.errors
    }


def test_source_primary_flag_must_match_originality_classification() -> None:
    data = _json("evidence-dossier.json")
    data["sources"][0]["originality"]["kind"] = "aggregation"

    _, report = validate_artifact_data("evidence", data)

    assert not report.valid
    assert ("schema_error", "/sources/0") in {(issue.code, issue.path) for issue in report.errors}


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("estimated_tokens",), "1200"),
        (("limits", "maximum_candidates"), "40"),
        (("sources", 0, "is_primary"), 1),
    ],
)
def test_json_scalar_types_are_strict(path: tuple[str | int, ...], value: object) -> None:
    data = _json("evidence-dossier.json")
    target: Any = data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    _, report = validate_artifact_data("evidence", data)

    assert not report.valid
    assert report.errors[0].code == "schema_error"


def test_date_and_datetime_fields_parse_iso_strings_but_reject_numbers() -> None:
    request = _json("collection-request.json")
    request["episode_date"] = 0
    _, date_report = validate_artifact_data("collection-request", request)

    evidence = _json("evidence-dossier.json")
    evidence["collection_started_at"] = 0
    _, datetime_report = validate_artifact_data("evidence", evidence)

    assert not date_report.valid
    assert not datetime_report.valid
    assert date_report.errors[0].code == "schema_error"
    assert datetime_report.errors[0].code == "schema_error"


def test_collection_request_carries_collection_context() -> None:
    data = _json("collection-request.json")

    artifact, report = validate_artifact_data("collection-request", data)

    assert report.valid
    assert isinstance(artifact, CollectionRequest)
    assert artifact.audience.knowledge_level == "informed_generalist"
    assert artifact.editorial_priorities.policy["avoid_sensationalism"] is True
    assert artifact.evidence_contract_version == "1.0"


def test_published_asset_urls_require_https() -> None:
    data = _json("published-episode.json")
    data["assets"][0]["public_url"] = "http://podcast.example.invalid/episode.mp3"

    _, report = validate_artifact_data("published-episode", data)

    assert not report.valid
    assert ("schema_error", "/assets/0/public_url") in {
        (issue.code, issue.path) for issue in report.errors
    }


def test_invalid_json_shape_and_unknown_type_are_concise() -> None:
    _, shape_report = validate_artifact_data("evidence", [])
    _, type_report = validate_artifact_data("not-real", {"contract_version": "1.0"})

    assert shape_report.errors[0].code == "schema_error"
    assert type_report.errors[0].code == "unknown_artifact_type"
    assert set(ARTIFACT_TYPES) == {
        "collection-request",
        "evidence",
        "plan",
        "script",
        "published-episode",
        "run-state",
    }


def test_operational_identifiers_reject_path_syntax() -> None:
    request = _json("collection-request.json")
    request["run_id"] = "../outside"

    _, report = validate_artifact_data("collection-request", request)

    assert not report.valid
    assert ("schema_error", "/run_id") in {(issue.code, issue.path) for issue in report.errors}


def test_concise_report_bounds_issue_output() -> None:
    errors = tuple(
        type(validate_artifact_data("evidence", [])[1].errors[0])(
            code="schema_error", path=f"/{index}", message="invalid"
        )
        for index in range(12)
    )
    report = ValidationReport("evidence", False, errors, ())

    assert len(cast(list[object], report.to_dict(concise=True)["errors"])) == 10
