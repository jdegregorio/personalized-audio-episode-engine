"""Verify committed artifact schemas and synthetic contract fixtures."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from pydantic import JsonValue

from audio_engine.artifacts import (
    ARTIFACT_SCHEMA_FILENAMES,
    EditorialPlan,
    EpisodeScript,
    EvidenceDossier,
    artifact_json_schemas,
)
from audio_engine.validation import (
    load_artifact_file,
    validate_artifact_data,
    validate_plan_against_dossier,
    validate_script_against_plan_and_dossier,
)

_SYNTHETIC_OUTPUT_ROOT = Path("/synthetic/run")


class _ValidFixture(TypedDict):
    type: str
    file: str


class _FixtureOperation(TypedDict):
    op: str
    path: str
    value: NotRequired[JsonValue]


class _InvalidFixture(TypedDict):
    name: str
    type: str
    base: str
    operations: list[_FixtureOperation]
    expected_code: str
    expected_path: str


class _FixtureManifest(TypedDict):
    valid: list[_ValidFixture]
    invalid: list[_InvalidFixture]
    rss: str


def _load_manifest(path: Path) -> _FixtureManifest:
    return cast(
        _FixtureManifest,
        json.loads(path.read_text(encoding="utf-8")),
    )


def materialize_invalid_fixture(fixture_root: Path, fixture: _InvalidFixture) -> JsonValue:
    """Apply the manifest's small replace/remove subset to a golden JSON value."""
    value = cast(
        JsonValue,
        json.loads((fixture_root / fixture["base"]).read_text(encoding="utf-8")),
    )
    value = copy.deepcopy(value)
    for operation in fixture["operations"]:
        tokens = [
            token.replace("~1", "/").replace("~0", "~")
            for token in operation["path"].removeprefix("/").split("/")
        ]
        parent = value
        for token in tokens[:-1]:
            if isinstance(parent, dict):
                parent = parent[token]
            elif isinstance(parent, list):
                parent = parent[int(token)]
            else:
                raise ValueError(f"fixture path is not traversable: {operation['path']}")
        final = tokens[-1]
        if operation["op"] == "remove":
            if isinstance(parent, dict):
                parent.pop(final)
            elif isinstance(parent, list):
                parent.pop(int(final))
            else:
                raise ValueError(f"fixture path is not removable: {operation['path']}")
        elif operation["op"] == "replace":
            if "value" not in operation:
                raise ValueError(f"replacement fixture value is missing: {operation['path']}")
            replacement = copy.deepcopy(operation["value"])
            if isinstance(parent, dict):
                parent[final] = replacement
            elif isinstance(parent, list):
                parent[int(final)] = replacement
            else:
                raise ValueError(f"fixture path is not replaceable: {operation['path']}")
        else:
            raise ValueError(f"unsupported fixture operation: {operation['op']}")
    return value


def artifact_contract_errors(root: Path) -> list[str]:
    """Return drift or fixture errors without touching production state."""
    errors: list[str] = []
    for artifact_type, generated in artifact_json_schemas().items():
        path = root / "schemas" / ARTIFACT_SCHEMA_FILENAMES[artifact_type]
        try:
            committed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            errors.append(f"missing or invalid schema: {path.relative_to(root)}")
            continue
        if committed != generated:
            errors.append(f"schema drift: {path.relative_to(root)}")

    fixture_root = root / "tests" / "fixtures" / "artifacts"
    try:
        manifest = _load_manifest(fixture_root / "manifest.json")
    except (OSError, UnicodeError, json.JSONDecodeError):
        return [*errors, "missing or invalid artifact fixture manifest"]

    valid_models: dict[str, object] = {}
    for fixture in manifest["valid"]:
        path = fixture_root / fixture["file"]
        output_roots = [_SYNTHETIC_OUTPUT_ROOT] if fixture["type"] == "collection-request" else []
        model, report = load_artifact_file(
            fixture["type"],
            path,
            allowed_output_roots=output_roots,
        )
        if not report.valid or model is None:
            errors.append(f"valid fixture rejected: {fixture['file']}")
        else:
            valid_models[fixture["type"]] = model

    for fixture in manifest["invalid"]:
        try:
            data = materialize_invalid_fixture(fixture_root, fixture)
        except (
            KeyError,
            IndexError,
            OSError,
            TypeError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
        ):
            errors.append(f"invalid fixture definition: {fixture['name']}")
            continue
        _, report = validate_artifact_data(fixture["type"], data)
        expected = (fixture["expected_code"], fixture["expected_path"])
        actual = {(issue.code, issue.path) for issue in report.errors}
        if report.valid or expected not in actual:
            errors.append(f"invalid fixture did not produce {expected}: {fixture['name']}")

    evidence = valid_models.get("evidence")
    plan = valid_models.get("plan")
    script = valid_models.get("script")
    if (
        isinstance(evidence, EvidenceDossier)
        and isinstance(plan, EditorialPlan)
        and isinstance(script, EpisodeScript)
    ):
        if validate_plan_against_dossier(plan, evidence):
            errors.append("valid editorial plan fails evidence cross-validation")
        if validate_script_against_plan_and_dossier(script, plan, evidence):
            errors.append("valid episode script fails lineage cross-validation")
    else:
        errors.append("cross-artifact golden fixtures are unavailable")

    rss_path = fixture_root / manifest["rss"]
    try:
        rss_root = ET.parse(rss_path).getroot()
    except (OSError, ET.ParseError):
        errors.append(f"invalid RSS golden fixture: {manifest['rss']}")
    else:
        if rss_root.tag != "rss" or rss_root.find("channel/item/enclosure") is None:
            errors.append(f"incomplete RSS golden fixture: {manifest['rss']}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    errors = artifact_contract_errors(root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("artifact contracts: ok")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CI and smoke commands
    raise SystemExit(main())
