"""Path, object-key, date, and redaction safety helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REDACTED = "<redacted>"
REDACTED_LOCATION = "<redacted-object-location>"
EPISODE_ASSET_NAMES = frozenset(
    {"episode.mp3", "transcript.txt", "show-notes.html", "episode.json"}
)
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class SafetyError(ValueError):
    """A path or key crossed a configured safety boundary."""


def is_safe_object_key_segment(value: str) -> bool:
    """Return whether a value uses the shared ASCII object-key segment alphabet."""
    return _SAFE_SEGMENT.fullmatch(value) is not None


@dataclass(frozen=True)
class LocalPathPolicy:
    """Resolve runtime, staging, and input paths against distinct configured roots."""

    runtime_root: Path
    staging_root: Path
    input_roots: tuple[Path, ...]

    def runtime(self, path: Path, *, must_exist: bool = False) -> Path:
        return resolve_within_roots(path, [self.runtime_root], must_exist=must_exist)

    def staging(self, path: Path, *, must_exist: bool = False) -> Path:
        return resolve_within_roots(path, [self.staging_root], must_exist=must_exist)

    def input(self, path: Path, *, must_exist: bool = True) -> Path:
        return resolve_within_roots(path, self.input_roots, must_exist=must_exist)


def resolve_within_roots(
    path: Path,
    allowed_roots: Sequence[Path],
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve a path and require it to remain below one configured root."""
    if not allowed_roots:
        raise SafetyError("no allowed roots are configured")
    try:
        resolved = path.expanduser().resolve(strict=must_exist)
    except OSError:
        raise SafetyError("path does not exist or cannot be resolved") from None
    resolved_roots = [root.expanduser().resolve() for root in allowed_roots]
    if not any(resolved.is_relative_to(root) for root in resolved_roots):
        raise SafetyError("path is outside the configured roots")
    return resolved


class ObjectKeyPolicy:
    """Construct and validate keys below one secret feed token's roots."""

    def __init__(self, feed_token: str) -> None:
        if len(feed_token) < 32 or not is_safe_object_key_segment(feed_token):
            raise SafetyError("feed token is not a safe key segment")
        self._feed_token = feed_token

    @property
    def feed_prefix(self) -> str:
        return f"feeds/{self._feed_token}/"

    @property
    def episode_prefix(self) -> str:
        return f"episodes/{self._feed_token}/"

    def feed_key(self) -> str:
        return f"{self.feed_prefix}feed.xml"

    def episode_key(self, profile_id: str, episode_date: date, asset_name: str) -> str:
        if not is_safe_object_key_segment(profile_id):
            raise SafetyError("profile identifier is not a safe key segment")
        if asset_name not in EPISODE_ASSET_NAMES:
            raise SafetyError("episode asset name is not allowed")
        key = f"{self.episode_prefix}{profile_id}-{episode_date.isoformat()}/{asset_name}"
        return self.validate(key, root="episode")

    def validate(self, key: str, *, root: Literal["feed", "episode"]) -> str:
        prefix = self.feed_prefix if root == "feed" else self.episode_prefix
        path = PurePosixPath(key)
        if (
            key.startswith("/")
            or "\\" in key
            or "//" in key
            or any(part in {"", ".", ".."} for part in path.parts)
            or not key.startswith(prefix)
        ):
            raise SafetyError(f"object key is outside the configured {root} prefix")
        return key


def resolve_episode_date(timezone_name: str, *, now: datetime | None = None) -> date:
    """Resolve the local episode date from an aware instant and IANA timezone."""
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise SafetyError("profile timezone is not available") from None
    instant = datetime.now(UTC) if now is None else now
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise SafetyError("episode-date resolution requires a timezone-aware instant")
    return instant.astimezone(timezone).date()


def redact_text(
    text: str,
    *,
    sensitive_values: Iterable[str] = (),
    feed_token: str | None = None,
) -> str:
    """Redact configured secrets and complete tokenized URLs/object keys."""
    redacted = text
    if feed_token:
        token = re.escape(feed_token)
        location = re.compile(rf"(?:https://[^\s]+)?(?:feeds|episodes)/{token}/[^\s]*")
        redacted = location.sub(REDACTED_LOCATION, redacted)
        redacted = redacted.replace(feed_token, REDACTED)
    values = sorted((value for value in sensitive_values if value), key=len, reverse=True)
    for value in values:
        redacted = redacted.replace(value, REDACTED)
    return redacted
