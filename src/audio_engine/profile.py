"""Versioned, topic-generic episode profile models and YAML loading."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from audio_engine.safety import resolve_within_roots

PROFILE_SCHEMA_VERSION = "1.0"
SUPPORTED_PROFILE_SCHEMA_VERSIONS = frozenset({PROFILE_SCHEMA_VERSION})

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*$", min_length=1, max_length=80)]
NonEmptyText = Annotated[str, Field(min_length=1, max_length=2_000)]


class ProfileError(ValueError):
    """A safe, operator-facing profile failure."""


class UnsupportedProfileVersion(ProfileError):
    """The profile requires a schema version this engine does not support."""


class _ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(_ProfileModel):
    feed_id: Identifier
    title_template: NonEmptyText
    description: NonEmptyText

    @field_validator("title_template")
    @classmethod
    def require_date_placeholder(cls, value: str) -> str:
        if "{date}" not in value:
            raise ValueError("title_template must contain {date}")
        return value


class ScopeSection(_ProfileModel):
    id: Identifier
    description: NonEmptyText


class EpisodeScope(_ProfileModel):
    sections: Annotated[list[ScopeSection], Field(min_length=1, max_length=30)]
    exclude: Annotated[list[NonEmptyText], Field(max_length=100)] = Field(default_factory=list)

    @field_validator("sections")
    @classmethod
    def unique_sections(cls, value: list[ScopeSection]) -> list[ScopeSection]:
        identifiers = [section.id for section in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("scope section identifiers must be unique")
        return value


class Episode(_ProfileModel):
    topic: NonEmptyText
    scope: EpisodeScope


class Audience(_ProfileModel):
    timezone: NonEmptyText
    locale: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")]
    knowledge_level: Identifier
    preferences: Annotated[list[NonEmptyText], Field(max_length=100)] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone name") from error
        return value


class TimeWindow(_ProfileModel):
    recency_hours: Annotated[int, Field(ge=1, le=24 * 14)]


class Collection(_ProfileModel):
    source_types: Annotated[list[Identifier], Field(min_length=1, max_length=20)]
    suggested_capabilities: Annotated[list[Identifier], Field(max_length=20)] = Field(
        default_factory=list
    )
    required_capabilities: Annotated[list[Identifier], Field(max_length=20)] = Field(
        default_factory=list
    )
    allow_native_research_fallback: bool
    evidence_contract_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    time_window: TimeWindow
    target_candidates: dict[Identifier, Annotated[int, Field(ge=0, le=1_000)]]
    maximum_candidates: Annotated[int, Field(ge=1, le=5_000)]
    maximum_sources: Annotated[int, Field(ge=1, le=10_000)]
    warning_estimated_tokens: Annotated[int, Field(ge=1, le=1_000_000)] = 50_000
    maximum_estimated_tokens: Annotated[int, Field(ge=1, le=2_000_000)] = 100_000

    @model_validator(mode="after")
    def ordered_token_limits(self) -> Collection:
        if self.warning_estimated_tokens > self.maximum_estimated_tokens:
            raise ValueError("warning_estimated_tokens must not exceed maximum_estimated_tokens")
        return self


class SectionTarget(_ProfileModel):
    minimum_items: Annotated[int, Field(ge=0, le=100)]
    maximum_items: Annotated[int, Field(ge=0, le=100)]

    @model_validator(mode="after")
    def ordered_bounds(self) -> SectionTarget:
        if self.minimum_items > self.maximum_items:
            raise ValueError("minimum_items must not exceed maximum_items")
        return self


class Editorial(_ProfileModel):
    target_minutes: Annotated[int, Field(ge=1, le=180)]
    minimum_minutes: Annotated[int, Field(ge=1, le=180)]
    maximum_minutes: Annotated[int, Field(ge=1, le=180)]
    target_sections: dict[Identifier, SectionTarget]
    maximum_total_items: Annotated[int, Field(ge=1, le=100)]
    allow_empty_sections: list[Identifier] = Field(default_factory=list)
    exclusion_reason_codes: list[Identifier] = Field(default_factory=list)
    policy: dict[Identifier, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered_duration(self) -> Editorial:
        if not self.minimum_minutes <= self.target_minutes <= self.maximum_minutes:
            raise ValueError("target_minutes must be within minimum_minutes and maximum_minutes")
        return self

    @field_validator("allow_empty_sections", "exclusion_reason_codes")
    @classmethod
    def unique_editorial_identifiers(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("editorial identifier lists must contain unique values")
        return value


class Speaker(_ProfileModel):
    name: NonEmptyText
    voice: NonEmptyText
    profile: NonEmptyText


class Hosts(_ProfileModel):
    format: Literal["two_speaker"]
    relationship: NonEmptyText
    female: Speaker
    male: Speaker


class Performance(_ProfileModel):
    style: NonEmptyText
    pace: NonEmptyText
    use_audio_tags: Literal["never", "sparingly", "freely"]
    prohibit_fake_personal_experience: bool
    prohibit_urls_in_speech: bool


class Tts(_ProfileModel):
    provider: Identifier
    model: NonEmptyText
    safe_input_tokens: Annotated[int, Field(ge=1, le=8_192)]
    target_segment_minutes: Annotated[int, Field(ge=1, le=10)]
    maximum_retries: Annotated[int, Field(ge=0, le=10)]


class Publishing(_ProfileModel):
    feed_title: NonEmptyText
    language: Annotated[str, Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")]
    provider: Literal["cloudflare_r2"]
    private_path_env: Literal["PODCAST_FEED_TOKEN"]
    endpoint_url_env: Literal["R2_ENDPOINT_URL"]
    bucket_name_env: Literal["R2_BUCKET_NAME"]
    base_url_env: Literal["PODCAST_BASE_URL"]
    retention_days_env: Literal["R2_RETENTION_DAYS"]


class EpisodeProfile(_ProfileModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:personalized-audio-episode-engine:schema:episode-profile:1.0",
        },
    )

    schema_version: Literal["1.0"]
    id: Identifier
    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    enabled: bool
    identity: Identity
    episode: Episode
    audience: Audience
    collection: Collection
    editorial: Editorial
    hosts: Hosts
    performance: Performance
    tts: Tts
    publishing: Publishing

    @model_validator(mode="after")
    def validate_section_references(self) -> EpisodeProfile:
        section_ids = {section.id for section in self.episode.scope.sections}
        references = (
            set(self.collection.target_candidates)
            | set(self.editorial.target_sections)
            | set(self.editorial.allow_empty_sections)
        )
        unknown = sorted(references - section_ids)
        if unknown:
            raise ValueError(f"section references are not declared in episode.scope: {unknown}")
        return self


def validate_profile_data(data: object) -> EpisodeProfile:
    """Validate decoded profile data with an explicit version compatibility check."""
    if not isinstance(data, dict):
        raise ProfileError("profile root must be a YAML mapping")
    mapping = cast(dict[str, object], data)
    version = mapping.get("schema_version")
    if version not in SUPPORTED_PROFILE_SCHEMA_VERSIONS:
        supported = ", ".join(sorted(SUPPORTED_PROFILE_SCHEMA_VERSIONS))
        raise UnsupportedProfileVersion(
            f"unsupported profile schema_version {version!r}; supported: {supported}"
        )
    try:
        return EpisodeProfile.model_validate(mapping)
    except ValidationError as error:
        problems = sorted(
            {
                f"{'.'.join(str(part) for part in item['loc']) or '<profile>'}: {item['msg']}"
                for item in error.errors()
            }
        )
        raise ProfileError(f"profile validation failed at: {', '.join(problems)}") from None


def load_profile(path: Path, *, allowed_roots: Sequence[Path]) -> EpisodeProfile:
    """Safely load and validate a YAML profile below an allowed input root."""
    safe_path = resolve_within_roots(path, allowed_roots, must_exist=True)
    if not safe_path.is_file():
        raise ProfileError("profile path must be a file")
    try:
        data = yaml.safe_load(safe_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError):
        raise ProfileError("profile YAML is unreadable, malformed, or unsafe") from None
    return validate_profile_data(data)


def profile_json_schema() -> dict[str, object]:
    """Return the canonical JSON Schema representation of the profile model."""
    return EpisodeProfile.model_json_schema()
