"""Typed environment configuration for local and provider boundaries."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from audio_engine.safety import is_safe_object_key_segment


class EngineSettings(BaseSettings):
    """Validated settings loaded from the process environment only."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        extra="ignore",
        validate_default=True,
    )

    gemini_api_key: SecretStr = Field(validation_alias="GEMINI_API_KEY")
    podcast_feed_token: SecretStr = Field(validation_alias="PODCAST_FEED_TOKEN")
    r2_access_key_id: SecretStr = Field(validation_alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: SecretStr = Field(validation_alias="R2_SECRET_ACCESS_KEY")
    r2_endpoint_url: HttpUrl = Field(validation_alias="R2_ENDPOINT_URL")
    r2_bucket_name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")] = Field(
        validation_alias="R2_BUCKET_NAME"
    )
    podcast_base_url: HttpUrl = Field(validation_alias="PODCAST_BASE_URL")
    r2_retention_days: Annotated[int, Field(ge=1, le=3_650)] = Field(
        validation_alias="R2_RETENTION_DAYS"
    )
    runtime_root: Path = Field(validation_alias="AUDIO_ENGINE_RUNTIME_ROOT")
    staging_root: Path = Field(validation_alias="AUDIO_ENGINE_STAGING_ROOT")
    input_roots: Annotated[tuple[Path, ...], NoDecode] = Field(
        default=(), validation_alias="AUDIO_ENGINE_INPUT_ROOTS"
    )
    maximum_run_age_seconds: Annotated[int, Field(ge=60, le=7 * 24 * 60 * 60)] = Field(
        default=6 * 60 * 60,
        validation_alias="AUDIO_ENGINE_MAX_RUN_AGE_SECONDS",
    )

    @field_validator("podcast_feed_token")
    @classmethod
    def valid_feed_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if len(token) < 32 or not is_safe_object_key_segment(token):
            raise ValueError("feed token must be at least 32 URL-safe characters")
        return value

    @field_validator("gemini_api_key", "r2_access_key_id", "r2_secret_access_key")
    @classmethod
    def non_empty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("credential must not be empty")
        return value

    @field_validator("r2_endpoint_url", "podcast_base_url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("URL must use HTTPS")
        if value.path not in {"", "/"} or value.query or value.fragment:
            raise ValueError("URL must be an HTTPS origin without path, query, or fragment")
        return value

    @field_validator("runtime_root", "staging_root")
    @classmethod
    def absolute_root(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("configured roots must be absolute")
        return value

    @field_validator("input_roots", mode="before")
    @classmethod
    def parse_input_roots(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(Path(item) for item in value.split(os.pathsep) if item)
        return value

    @field_validator("input_roots")
    @classmethod
    def absolute_input_roots(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        if any(not root.is_absolute() for root in value):
            raise ValueError("configured input roots must be absolute")
        return value

    @model_validator(mode="after")
    def distinct_output_roots(self) -> Self:
        try:
            runtime_root = self.runtime_root.resolve()
            staging_root = self.staging_root.resolve()
        except (OSError, RuntimeError) as error:
            raise ValueError("runtime and staging roots must be resolvable") from error
        if runtime_root == staging_root:
            raise ValueError("runtime and staging roots must be distinct")
        return self

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> EngineSettings:
        """Validate an explicit mapping without reading the developer's environment."""
        return cls.model_validate(dict(values))

    @classmethod
    def from_environment(cls) -> EngineSettings:
        """Load the process environment through the BaseSettings source chain."""
        return cls()  # pyright: ignore[reportCallIssue]
