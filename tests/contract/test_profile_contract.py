from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from audio_engine.profile import profile_json_schema, validate_profile_data


def test_committed_schema_matches_python_model() -> None:
    schema_path = Path(__file__).parents[2] / "schemas" / "episode-profile-v1.0.schema.json"
    committed = json.loads(schema_path.read_text(encoding="utf-8"))

    assert committed == profile_json_schema()


def test_unrelated_profile_uses_same_contract(example_profile_data: dict[str, Any]) -> None:
    example_profile_data["id"] = "open-source-release-notes"
    example_profile_data["episode"]["topic"] = "Open source project releases"
    example_profile_data["episode"]["scope"]["sections"] = [
        {"id": "languages", "description": "Language releases"},
        {"id": "databases", "description": "Database releases"},
    ]
    example_profile_data["collection"]["target_candidates"] = {"languages": 5, "databases": 5}
    example_profile_data["editorial"]["target_sections"] = {
        "languages": {"minimum_items": 1, "maximum_items": 3},
        "databases": {"minimum_items": 1, "maximum_items": 3},
    }
    example_profile_data["editorial"]["allow_empty_sections"] = []

    profile = validate_profile_data(example_profile_data)

    assert profile.id == "open-source-release-notes"
    assert profile.editorial.policy["source_policy"] == "fact_first"
