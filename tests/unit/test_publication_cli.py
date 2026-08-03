from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.publish_episode as publish_script
import scripts.smoke_r2 as smoke_script
from audio_engine.publication import (
    ObjectHead,
    PreconditionFailed,
    PublicationError,
    PublicationResult,
    StoredObject,
)
from audio_engine.storage import sha256_bytes
from tests.tts_support import configure_environment


def test_publish_cli_reports_success_and_deferred_exit(
    tmp_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)
    run = tmp_path / "run"
    run.mkdir()
    outcomes = iter(
        [
            PublicationResult("published", "marine-brief:2026-01-15", 4),
            PublicationResult("deferred", "marine-brief:2026-01-15", 4),
        ]
    )

    def publish(*args: object, **kwargs: object) -> PublicationResult:
        del args, kwargs
        return next(outcomes)

    monkeypatch.setattr(publish_script, "publish_episode", publish)

    assert publish_script.main(["--run", str(run)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "published"
    assert publish_script.main(["--run", str(run)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "deferred"


def test_publish_cli_failure_is_concise_and_does_not_echo_settings(
    tmp_path: Path,
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)

    def fail(*args: object, **kwargs: object) -> PublicationResult:
        del args, kwargs
        raise PublicationError("safe publication failure")

    monkeypatch.setattr(publish_script, "publish_episode", fail)
    assert publish_script.main(["--run", str(tmp_path)]) == 1
    error = capsys.readouterr().err
    assert "safe publication failure" in error
    assert settings_values["PODCAST_FEED_TOKEN"] not in error
    assert settings_values["R2_SECRET_ACCESS_KEY"] not in error


class _ProbeStore:
    deleted = False

    def __init__(self, settings: object) -> None:
        del settings
        self.body = b""
        self.media_type = ""
        self.digest = ""
        self.etag = '"probe-etag-0"'
        self.revision = 0

    def put(self, key: str, body: bytes, **kwargs: object) -> str:
        assert key.startswith("probes/r2-smoke-")
        if_match = kwargs.get("if_match")
        if if_match is not None and if_match != self.etag:
            raise PreconditionFailed("conditional R2 object write failed")
        self.body = body
        self.media_type = str(kwargs["content_type"])
        self.digest = str(kwargs["sha256"])
        self.revision += 1
        self.etag = f'"probe-etag-{self.revision}"'
        return self.etag

    def get(self, key: str) -> StoredObject:
        del key
        return StoredObject(
            self.body,
            self.etag,
            self.media_type,
            "no-store",
            self.digest,
        )

    def head(self, key: str) -> ObjectHead:
        del key
        return ObjectHead(
            self.etag,
            self.media_type,
            "no-store",
            len(self.body),
            self.digest,
        )

    def verify_public(self, key: str, **kwargs: object) -> None:
        del key
        assert kwargs["sha256"] == sha256_bytes(self.body)

    def delete(self, key: str) -> None:
        assert key.startswith("probes/r2-smoke-")
        type(self).deleted = True


def test_r2_smoke_cli_verifies_and_cleans_without_outputting_key(
    settings_values: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_environment(monkeypatch, settings_values)
    _ProbeStore.deleted = False
    monkeypatch.setattr(smoke_script, "R2ObjectStore", _ProbeStore)

    assert smoke_script.main([]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["result"] == "passed"
    assert result["cleanup"] == "completed"
    assert result["conditional_write"] == "passed"
    assert _ProbeStore.deleted
    assert "probes/" not in output
    assert settings_values["PODCAST_FEED_TOKEN"] not in output
