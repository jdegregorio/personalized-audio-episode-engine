"""Bounded boto3 adapter for the configured Cloudflare R2 bucket."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Any, Protocol, Self, cast

import boto3  # pyright: ignore[reportMissingTypeStubs]
import httpx
from botocore.config import Config  # pyright: ignore[reportMissingTypeStubs]
from botocore.exceptions import (  # pyright: ignore[reportMissingTypeStubs]
    BotoCoreError,
    ClientError,
)
from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from audio_engine.config import EngineSettings
from audio_engine.publication import (
    ObjectHead,
    PreconditionFailed,
    PublicationError,
    StoredObject,
    public_object_url,
)
from audio_engine.storage import sha256_bytes

_MAX_READ_BYTES = 2 * 1024 * 1024


class _ResponseBody(Protocol):
    def read(self, amount: int) -> bytes: ...

    def close(self) -> None: ...


class _S3Client(Protocol):
    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_object(self, **kwargs: Any) -> dict[str, Any]: ...


class R2ConnectionSettings(BaseSettings):
    """Only the values needed by an R2 publisher or disposable R2 probe."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        extra="ignore",
        validate_default=True,
    )

    access_key_id: SecretStr = Field(validation_alias="R2_ACCESS_KEY_ID")
    secret_access_key: SecretStr = Field(validation_alias="R2_SECRET_ACCESS_KEY")
    endpoint_url: HttpUrl = Field(validation_alias="R2_ENDPOINT_URL")
    bucket_name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")] = Field(
        validation_alias="R2_BUCKET_NAME"
    )
    base_url: HttpUrl = Field(validation_alias="PODCAST_BASE_URL")

    @field_validator("access_key_id", "secret_access_key")
    @classmethod
    def non_empty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("credential must not be empty")
        return value

    @field_validator("endpoint_url", "base_url")
    @classmethod
    def https_origin(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.path not in {"", "/"} or value.query or value.fragment:
            raise ValueError("R2 URLs must be HTTPS origins")
        return value

    @classmethod
    def from_engine_settings(cls, settings: EngineSettings) -> Self:
        return cls.model_validate(
            {
                "R2_ACCESS_KEY_ID": settings.r2_access_key_id,
                "R2_SECRET_ACCESS_KEY": settings.r2_secret_access_key,
                "R2_ENDPOINT_URL": settings.r2_endpoint_url,
                "R2_BUCKET_NAME": settings.r2_bucket_name,
                "PODCAST_BASE_URL": settings.podcast_base_url,
            }
        )


class R2ObjectStore:
    """S3-compatible object reads/writes plus public endpoint verification."""

    def __init__(
        self,
        settings: R2ConnectionSettings,
        *,
        client: _S3Client | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or cast(
            _S3Client,
            boto3.client(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                endpoint_url=str(settings.endpoint_url).rstrip("/"),
                region_name="auto",
                aws_access_key_id=settings.access_key_id.get_secret_value(),
                aws_secret_access_key=settings.secret_access_key.get_secret_value(),
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=10,
                    read_timeout=30,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            ),
        )

    @classmethod
    def from_engine_settings(cls, settings: EngineSettings) -> Self:
        return cls(R2ConnectionSettings.from_engine_settings(settings))

    def get(self, key: str) -> StoredObject | None:
        try:
            response = self._client.get_object(Bucket=self.settings.bucket_name, Key=key)
            stream = cast(_ResponseBody, response["Body"])
            try:
                body = stream.read(_MAX_READ_BYTES + 1)
            finally:
                stream.close()
            if len(body) > _MAX_READ_BYTES:
                raise PublicationError("remote object exceeds the safe read limit")
            metadata = cast(dict[str, object], response.get("Metadata") or {})
            declared_hash = _metadata_hash(metadata)
            actual_hash = sha256_bytes(body)
            if declared_hash is not None and declared_hash != actual_hash:
                raise PublicationError("remote object hash metadata is invalid")
            return StoredObject(
                body=body,
                etag=_required_etag(response),
                content_type=str(response.get("ContentType") or ""),
                cache_control=_optional_string(response.get("CacheControl")),
                sha256=actual_hash,
            )
        except ClientError as error:
            if _is_missing(error):
                return None
            raise PublicationError("R2 object read failed") from error
        except (BotoCoreError, OSError, KeyError, TypeError) as error:
            raise PublicationError("R2 object read failed") from error

    def put(
        self,
        key: str,
        body: bytes | Path,
        *,
        content_type: str,
        cache_control: str | None,
        sha256: str,
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str:
        parameters: dict[str, Any] = {
            "Bucket": self.settings.bucket_name,
            "Key": key,
            "ContentType": content_type,
            "Metadata": {"sha256": sha256.removeprefix("sha256:")},
        }
        if cache_control is not None:
            parameters["CacheControl"] = cache_control
        if if_match is not None:
            parameters["IfMatch"] = if_match
        if if_none_match:
            parameters["IfNoneMatch"] = "*"
        try:
            if isinstance(body, Path):
                with body.open("rb") as stream:
                    response = self._client.put_object(Body=stream, **parameters)
            else:
                response = self._client.put_object(Body=body, **parameters)
            return _required_etag(response)
        except ClientError as error:
            if _is_precondition(error):
                raise PreconditionFailed("conditional R2 object write failed") from None
            raise PublicationError("R2 object write failed") from error
        except (BotoCoreError, OSError, KeyError, TypeError) as error:
            raise PublicationError("R2 object write failed") from error

    def head(self, key: str) -> ObjectHead:
        try:
            response = self._client.head_object(Bucket=self.settings.bucket_name, Key=key)
            declared_hash = _metadata_hash(cast(dict[str, object], response.get("Metadata") or {}))
            if declared_hash is None:
                raise PublicationError("R2 object is missing hash metadata")
            return ObjectHead(
                etag=_required_etag(response),
                content_type=str(response.get("ContentType") or ""),
                cache_control=_optional_string(response.get("CacheControl")),
                bytes=int(response["ContentLength"]),
                sha256=declared_hash,
            )
        except PublicationError:
            raise
        except (ClientError, BotoCoreError, KeyError, TypeError, ValueError) as error:
            raise PublicationError("R2 object HEAD failed") from error

    def verify_public(
        self,
        key: str,
        *,
        content_type: str,
        bytes: int,
        sha256: str,
    ) -> None:
        url = public_object_url(str(self.settings.base_url), key)
        digest = hashlib.sha256()
        received = 0
        try:
            with httpx.stream(
                "GET",
                url,
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=False,
            ) as response:
                if response.status_code != 200:
                    raise PublicationError("public object fetch did not return HTTP 200")
                if _normalize_media_type(response.headers.get("content-type", "")) != (
                    _normalize_media_type(content_type)
                ):
                    raise PublicationError("public object media type is incorrect")
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > bytes:
                        raise PublicationError("public object length is incorrect")
                    digest.update(chunk)
        except PublicationError:
            raise
        except httpx.HTTPError as error:
            raise PublicationError("public object fetch failed") from error
        actual_hash = f"sha256:{digest.hexdigest()}"
        if received != bytes or actual_hash != sha256:
            raise PublicationError("public object body verification failed")

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.settings.bucket_name, Key=key)
        except (ClientError, BotoCoreError) as error:
            raise PublicationError("R2 object deletion failed") from error


def _required_etag(response: dict[str, Any]) -> str:
    value = response.get("ETag")
    if not isinstance(value, str) or not value:
        raise PublicationError("R2 response did not include an ETag")
    return value


def _metadata_hash(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = cast(dict[object, object], metadata).get("sha256")
    if not isinstance(value, str) or len(value) != 64:
        return None
    try:
        int(value, 16)
    except ValueError:
        return None
    return f"sha256:{value.lower()}"


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_media_type(value: str) -> str:
    return ";".join(part.strip().lower() for part in value.split(";"))


def _is_missing(error: ClientError) -> bool:
    response = cast(dict[str, Any], error.response)
    status = cast(dict[str, object], response.get("ResponseMetadata", {})).get("HTTPStatusCode")
    code = cast(dict[str, object], response.get("Error", {})).get("Code")
    return status == 404 or code in {"404", "NoSuchKey", "NotFound"}


def _is_precondition(error: ClientError) -> bool:
    response = cast(dict[str, Any], error.response)
    status = cast(dict[str, object], response.get("ResponseMetadata", {})).get("HTTPStatusCode")
    code = cast(dict[str, object], response.get("Error", {})).get("Code")
    return status == 412 or code in {"412", "PreconditionFailed"}
