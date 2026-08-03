from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
import respx
from botocore.exceptions import ClientError  # pyright: ignore[reportMissingTypeStubs]
from httpx import Response

from audio_engine.config import EngineSettings
from audio_engine.publication import PreconditionFailed, PublicationError
from audio_engine.r2 import R2ConnectionSettings, R2ObjectStore
from audio_engine.storage import sha256_bytes


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, Any]]] = {}
        self.put_calls: list[dict[str, Any]] = []
        self.put_error: ClientError | None = None
        self.get_error: ClientError | None = None
        self.head_error: ClientError | None = None
        self.delete_error: ClientError | None = None
        self.omit_etag = False

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.put_error is not None:
            raise self.put_error
        body = kwargs["Body"]
        payload = body.read() if hasattr(body, "read") else body
        call = {**kwargs, "Body": payload}
        self.put_calls.append(call)
        self.objects[str(kwargs["Key"])] = (payload, call)
        return {} if self.omit_etag else {"ETag": '"etag-1"'}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.get_error is not None:
            raise self.get_error
        key = str(kwargs["Key"])
        payload, stored = self.objects[key]
        return {
            "Body": io.BytesIO(payload),
            "ETag": '"etag-1"',
            "ContentType": stored["ContentType"],
            "CacheControl": stored.get("CacheControl"),
            "Metadata": stored["Metadata"],
        }

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.head_error is not None:
            raise self.head_error
        key = str(kwargs["Key"])
        payload, stored = self.objects[key]
        return {
            "ETag": '"etag-1"',
            "ContentType": stored["ContentType"],
            "CacheControl": stored.get("CacheControl"),
            "ContentLength": len(payload),
            "Metadata": stored["Metadata"],
        }

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        if self.delete_error is not None:
            raise self.delete_error
        self.objects.pop(str(kwargs["Key"]), None)
        return {}


def _settings() -> R2ConnectionSettings:
    return R2ConnectionSettings.model_validate(
        {
            "R2_ACCESS_KEY_ID": "access-key",
            "R2_SECRET_ACCESS_KEY": "secret-key",
            "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
            "R2_BUCKET_NAME": "audio-engine-test",
            "PODCAST_BASE_URL": "https://public.example.invalid",
        }
    )


def test_r2_adapter_writes_expected_headers_conditions_and_hash_metadata(tmp_path: Path) -> None:
    client = _FakeS3Client()
    store = R2ObjectStore(_settings(), client=client)
    path = tmp_path / "asset.txt"
    path.write_bytes(b"verified object")
    digest = sha256_bytes(path.read_bytes())

    etag = store.put(
        "probes/asset.txt",
        path,
        content_type="text/plain; charset=utf-8",
        cache_control="no-store",
        sha256=digest,
        if_none_match=True,
    )
    fetched = store.get("probes/asset.txt")
    head = store.head("probes/asset.txt")

    assert etag == '"etag-1"'
    assert client.put_calls[0]["IfNoneMatch"] == "*"
    assert client.put_calls[0]["ContentType"] == "text/plain; charset=utf-8"
    assert client.put_calls[0]["CacheControl"] == "no-store"
    assert client.put_calls[0]["Metadata"] == {"sha256": digest.removeprefix("sha256:")}
    assert fetched is not None and fetched.body == b"verified object"
    assert head.bytes == len(b"verified object") and head.sha256 == digest

    store.put(
        "probes/asset.txt",
        b"verified object",
        content_type="text/plain; charset=utf-8",
        cache_control="no-store",
        sha256=digest,
        if_match=etag,
    )
    assert client.put_calls[1]["IfMatch"] == etag


def test_r2_adapter_maps_precondition_failure_without_sensitive_context() -> None:
    client = _FakeS3Client()
    client.put_error = ClientError(
        {
            "Error": {"Code": "PreconditionFailed", "Message": "secret remote detail"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        },
        "PutObject",
    )
    store = R2ObjectStore(_settings(), client=client)

    with pytest.raises(PreconditionFailed, match="conditional R2") as captured:
        store.put(
            "feeds/sensitive-token/feed.xml",
            b"feed",
            content_type="application/rss+xml",
            cache_control="no-cache",
            sha256=sha256_bytes(b"feed"),
            if_none_match=True,
        )

    assert "sensitive-token" not in str(captured.value)
    assert "secret remote detail" not in str(captured.value)


@respx.mock
def test_r2_adapter_public_fetch_validates_media_size_and_hash() -> None:
    store = R2ObjectStore(_settings(), client=_FakeS3Client())
    payload = b"public body"
    route = respx.get("https://public.example.invalid/probes/asset.txt").mock(
        return_value=Response(
            200,
            content=payload,
            headers={"content-type": "text/plain; charset=utf-8"},
        )
    )

    store.verify_public(
        "probes/asset.txt",
        content_type="text/plain; charset=utf-8",
        bytes=len(payload),
        sha256=sha256_bytes(payload),
    )
    assert route.called

    with pytest.raises(PublicationError, match="body verification"):
        store.verify_public(
            "probes/asset.txt",
            content_type="text/plain; charset=utf-8",
            bytes=len(payload) + 1,
            sha256=sha256_bytes(payload),
        )


def test_r2_connection_settings_reject_paths_and_plain_http() -> None:
    values = {
        "R2_ACCESS_KEY_ID": "access-key",
        "R2_SECRET_ACCESS_KEY": "secret-key",
        "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com/path",
        "R2_BUCKET_NAME": "audio-engine-test",
        "PODCAST_BASE_URL": "http://public.example.invalid",
    }
    with pytest.raises(ValueError):
        R2ConnectionSettings.model_validate(values)


def test_r2_connection_settings_select_only_r2_values(
    settings_values: dict[str, str],
) -> None:
    engine = EngineSettings.from_mapping(settings_values)
    selected = R2ConnectionSettings.from_engine_settings(engine)

    assert selected.bucket_name == settings_values["R2_BUCKET_NAME"]
    assert selected.endpoint_url.host == "example.r2.cloudflarestorage.com"
    assert selected.access_key_id.get_secret_value() == settings_values["R2_ACCESS_KEY_ID"]


def _client_error(code: str, status: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "sensitive provider detail"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "SyntheticOperation",
    )


def test_r2_adapter_handles_missing_read_and_rejects_corrupt_hash_metadata() -> None:
    client = _FakeS3Client()
    client.get_error = _client_error("NoSuchKey", 404)
    store = R2ObjectStore(_settings(), client=client)
    assert store.get("missing") is None

    client.get_error = None
    body = b"body"
    store.put(
        "object",
        body,
        content_type="text/plain",
        cache_control=None,
        sha256=sha256_bytes(body),
    )
    client.objects["object"][1]["Metadata"] = {"sha256": "0" * 64}
    with pytest.raises(PublicationError, match="hash metadata"):
        store.get("object")

    client.objects["object"][1]["Metadata"] = {}
    with pytest.raises(PublicationError, match="missing hash"):
        store.head("object")


def test_r2_adapter_wraps_nonconditional_write_head_delete_and_etag_failures() -> None:
    client = _FakeS3Client()
    store = R2ObjectStore(_settings(), client=client)
    client.put_error = _client_error("AccessDenied", 403)
    with pytest.raises(PublicationError, match="write failed"):
        store.put(
            "object",
            b"body",
            content_type="text/plain",
            cache_control=None,
            sha256=sha256_bytes(b"body"),
        )

    client.put_error = None
    client.omit_etag = True
    with pytest.raises(PublicationError, match="ETag"):
        store.put(
            "object",
            b"body",
            content_type="text/plain",
            cache_control=None,
            sha256=sha256_bytes(b"body"),
        )

    client.head_error = _client_error("AccessDenied", 403)
    with pytest.raises(PublicationError, match="HEAD failed"):
        store.head("object")
    client.delete_error = _client_error("AccessDenied", 403)
    with pytest.raises(PublicationError, match="deletion failed"):
        store.delete("object")


@respx.mock
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (Response(404), "HTTP 200"),
        (Response(200, content=b"body", headers={"content-type": "application/json"}), "media"),
        (
            Response(200, content=b"too long", headers={"content-type": "text/plain"}),
            "length",
        ),
    ],
)
def test_r2_public_fetch_fails_closed_on_status_media_or_length(
    response: Response,
    message: str,
) -> None:
    store = R2ObjectStore(_settings(), client=_FakeS3Client())
    respx.get("https://public.example.invalid/probes/asset.txt").mock(return_value=response)

    with pytest.raises(PublicationError, match=message):
        store.verify_public(
            "probes/asset.txt",
            content_type="text/plain",
            bytes=4,
            sha256=sha256_bytes(b"body"),
        )
