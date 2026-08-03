from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audio_engine.profile import (
    ProfileError,
    UnsupportedProfileVersion,
    load_profile,
    validate_profile_data,
)


def test_example_profile_validates(
    example_profile_path: Path, example_profile_data: dict[str, Any]
) -> None:
    profile = validate_profile_data(example_profile_data)

    assert profile.id == "world-us-seattle-news"
    assert (
        load_profile(example_profile_path, allowed_roots=[example_profile_path.parent]) == profile
    )


def test_profile_supports_arbitrary_section_identifiers(
    example_profile_data: dict[str, Any],
) -> None:
    example_profile_data["id"] = "marine-biology-weekly"
    example_profile_data["episode"]["topic"] = "Marine biology research"
    example_profile_data["episode"]["scope"]["sections"] = [
        {"id": "fieldwork", "description": "New field studies"},
        {"id": "methods", "description": "Research methods"},
    ]
    example_profile_data["collection"]["target_candidates"] = {"fieldwork": 4, "methods": 2}
    example_profile_data["editorial"]["target_sections"] = {
        "fieldwork": {"minimum_items": 1, "maximum_items": 3},
        "methods": {"minimum_items": 0, "maximum_items": 2},
    }
    example_profile_data["editorial"]["allow_empty_sections"] = ["methods"]
    example_profile_data["editorial"]["exclusion_reason_codes"] = ["limited_field_value"]
    example_profile_data["editorial"]["policy"] = {"taxonomic_depth": "family"}

    profile = validate_profile_data(example_profile_data)

    assert {section.id for section in profile.episode.scope.sections} == {"fieldwork", "methods"}
    assert profile.editorial.exclusion_reason_codes == ["limited_field_value"]


def test_profile_rejects_duplicate_editorial_identifiers(
    example_profile_data: dict[str, Any],
) -> None:
    example_profile_data["editorial"]["exclusion_reason_codes"] = ["weak_source", "weak_source"]

    with pytest.raises(ProfileError, match="unique"):
        validate_profile_data(example_profile_data)


def test_profile_rejects_duplicate_fatal_script_warnings(
    example_profile_data: dict[str, Any],
) -> None:
    example_profile_data["performance"]["fatal_warning_codes"] = [
        "host_word_share",
        "host_word_share",
    ]

    with pytest.raises(ProfileError, match="fatal warning codes must be unique"):
        validate_profile_data(example_profile_data)


def test_profile_rejects_unknown_fatal_script_warning(
    example_profile_data: dict[str, Any],
) -> None:
    example_profile_data["performance"]["fatal_warning_codes"] = ["unknown_warning"]

    with pytest.raises(ProfileError, match="performance.fatal_warning_codes"):
        validate_profile_data(example_profile_data)


def test_profile_requires_distinct_host_names(example_profile_data: dict[str, Any]) -> None:
    example_profile_data["hosts"]["male"]["name"] = example_profile_data["hosts"]["female"]["name"]

    with pytest.raises(ProfileError, match="configured host names must be distinct"):
        validate_profile_data(example_profile_data)


def test_profile_rejects_unsupported_or_unquoted_version(
    example_profile_data: dict[str, Any],
) -> None:
    example_profile_data["schema_version"] = "2.0"
    with pytest.raises(UnsupportedProfileVersion, match="supported: 1.0"):
        validate_profile_data(example_profile_data)

    example_profile_data["schema_version"] = 1.0
    with pytest.raises(UnsupportedProfileVersion, match="schema_version 1.0"):
        validate_profile_data(example_profile_data)


def test_profile_rejects_unknown_section_reference(example_profile_data: dict[str, Any]) -> None:
    example_profile_data["collection"]["target_candidates"]["engine_defined"] = 1

    with pytest.raises(ProfileError, match="profile validation failed"):
        validate_profile_data(example_profile_data)


def test_profile_rejects_inverted_collection_token_limits(
    example_profile_data: dict[str, Any],
) -> None:
    example_profile_data["collection"]["warning_estimated_tokens"] = 100_001
    example_profile_data["collection"]["maximum_estimated_tokens"] = 100_000

    with pytest.raises(ProfileError, match="warning_estimated_tokens"):
        validate_profile_data(example_profile_data)


def test_profile_requires_publication_environment_names(
    example_profile_data: dict[str, Any],
) -> None:
    example_profile_data["publishing"]["endpoint_url_env"] = "https://embedded.invalid"

    with pytest.raises(ProfileError, match="publishing.endpoint_url_env"):
        validate_profile_data(example_profile_data)


@pytest.mark.parametrize(
    "content",
    [
        "schema_version: [",
        'schema_version: "1.0"\nvalue: !!python/object/apply:os.system ["false"]\n',
    ],
)
def test_profile_rejects_malformed_and_executable_yaml(tmp_path: Path, content: str) -> None:
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(content, encoding="utf-8")

    with pytest.raises(ProfileError, match="malformed, or unsafe"):
        load_profile(profile_path, allowed_roots=[tmp_path])


def test_profile_rejects_symlink_outside_input_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    target = outside / "profile.yaml"
    target.write_text('schema_version: "1.0"\n', encoding="utf-8")
    link = allowed / "profile.yaml"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="outside the configured roots"):
        load_profile(link, allowed_roots=[allowed])
