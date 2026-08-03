from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from audio_engine.safety import (
    REDACTED,
    REDACTED_LOCATION,
    LocalPathPolicy,
    ObjectKeyPolicy,
    SafetyError,
    redact_text,
    resolve_episode_date,
    resolve_within_roots,
)


def test_resolve_within_roots_accepts_child_and_rejects_traversal(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    child = allowed / "child.txt"
    child.write_text("safe", encoding="utf-8")

    assert resolve_within_roots(child, [allowed], must_exist=True) == child.resolve()
    with pytest.raises(SafetyError, match="outside"):
        resolve_within_roots(allowed / ".." / "outside.txt", [allowed])


def test_local_path_policy_keeps_runtime_staging_and_inputs_separate(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    staging = tmp_path / "staging"
    inputs = tmp_path / "inputs"
    for root in (runtime, staging, inputs):
        root.mkdir()
    policy = LocalPathPolicy(runtime, staging, (inputs,))

    assert policy.runtime(runtime / "runs" / "one") == runtime / "runs" / "one"
    assert policy.staging(staging / "episode.mp3") == staging / "episode.mp3"
    with pytest.raises(SafetyError, match="outside"):
        policy.input(runtime / "profile.yaml", must_exist=False)


def test_object_key_policy_constructs_only_configured_roots() -> None:
    policy = ObjectKeyPolicy("t" * 43)

    assert policy.feed_key() == f"feeds/{'t' * 43}/feed.xml"
    assert policy.episode_key("profile-one", date(2026, 8, 3), "episode.mp3") == (
        f"episodes/{'t' * 43}/profile-one-2026-08-03/episode.mp3"
    )
    with pytest.raises(SafetyError, match="outside"):
        policy.validate(f"episodes/{'t' * 43}/../other/file", root="episode")
    with pytest.raises(SafetyError, match="outside"):
        policy.validate(f"episodes/{'t' * 43}//other/file", root="episode")
    with pytest.raises(SafetyError, match="asset name"):
        policy.episode_key("profile-one", date(2026, 8, 3), "../feed.xml")


def test_episode_date_uses_profile_timezone_across_midnight() -> None:
    instant = datetime(2026, 8, 3, 6, 30, tzinfo=UTC)

    assert resolve_episode_date("America/Los_Angeles", now=instant) == date(2026, 8, 2)
    assert resolve_episode_date("Asia/Tokyo", now=instant) == date(2026, 8, 3)
    with pytest.raises(SafetyError, match="timezone-aware"):
        resolve_episode_date("UTC", now=datetime(2026, 8, 3))


def test_redaction_removes_secrets_and_complete_tokenized_locations() -> None:
    token = "t" * 43
    text = (
        f"key=gemini-secret id=r2-access secret=r2-secret token={token} "
        f"https://public.invalid/feeds/{token}/feed.xml "
        f"episodes/{token}/profile-2026-08-03/episode.mp3"
    )

    redacted = redact_text(
        text,
        sensitive_values=["gemini-secret", "r2-access", "r2-secret"],
        feed_token=token,
    )

    assert "gemini-secret" not in redacted
    assert "r2-access" not in redacted
    assert "r2-secret" not in redacted
    assert token not in redacted
    assert REDACTED in redacted
    assert redacted.count(REDACTED_LOCATION) == 2
