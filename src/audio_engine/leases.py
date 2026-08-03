"""Atomic, owner-checked episode leases for the local runtime root."""

from __future__ import annotations

import fcntl
import hashlib
import os
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from audio_engine.artifacts import EpisodeKey, JsonAwareDatetime, RunId, RunState
from audio_engine.storage import atomic_write_json, sync_directory
from audio_engine.validation import load_artifact_file

LEASE_CONTRACT_VERSION = "1.0"
_MAX_LEASE_BYTES = 64 * 1024


class LeaseError(RuntimeError):
    """A lease is corrupt, unavailable, or owned by another run."""


class LeaseRecord(BaseModel):
    """Durable ownership record stored at the deterministic episode lock path."""

    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: Literal["1.0"]
    run_id: RunId
    episode_key: EpisodeKey
    created_at: JsonAwareDatetime
    last_heartbeat_at: JsonAwareDatetime

    @model_validator(mode="after")
    def ordered_timestamps(self) -> Self:
        if self.last_heartbeat_at < self.created_at:
            raise ValueError("last heartbeat must not precede lease creation")
        return self


@dataclass(frozen=True)
class LeaseAcquisition:
    acquired: bool
    lease: LeaseRecord
    recovered: bool = False


class LeaseManager:
    """Coordinate one active owner per canonical episode key."""

    def __init__(
        self,
        runtime_root: Path,
        *,
        maximum_age: timedelta,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if maximum_age <= timedelta(0):
            raise ValueError("maximum lease age must be positive")
        try:
            self.runtime_root = runtime_root.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise LeaseError("runtime root does not exist or cannot be resolved") from error
        if not self.runtime_root.is_dir():
            raise LeaseError("runtime root must be a directory")
        self.locks_root = self.runtime_root / "locks"
        self.maximum_age = maximum_age
        self._clock = clock or (lambda: datetime.now(UTC))

    def lease_path(self, episode_key: str) -> Path:
        digest = hashlib.sha256(episode_key.encode("utf-8")).hexdigest()
        return self.locks_root / f"episode-{digest}.json"

    def acquire(self, episode_key: str, run_id: str) -> LeaseAcquisition:
        """Acquire ownership, recover a safe stale owner, or report a live owner."""
        self.locks_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.lease_path(episode_key)
        recovered = False
        for _ in range(100):
            now = self._now()
            record = LeaseRecord(
                contract_version=LEASE_CONTRACT_VERSION,
                run_id=run_id,
                episode_key=episode_key,
                created_at=now,
                last_heartbeat_at=now,
            )
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags, 0o600)
            except FileExistsError:
                existing = self._inspect_existing(path, episode_key, now)
                if existing is not None:
                    return LeaseAcquisition(False, existing, recovered=False)
                recovered = True
                continue
            except OSError as error:
                raise LeaseError("episode lease could not be created") from error
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                self._write_descriptor(descriptor, record)
                sync_directory(self.locks_root)
            except OSError as error:
                with suppress(OSError):
                    path.unlink(missing_ok=True)
                raise LeaseError("episode lease could not be persisted") from error
            finally:
                os.close(descriptor)
            return LeaseAcquisition(True, record, recovered=recovered)
        raise LeaseError("episode lease acquisition did not converge")

    def refresh(self, episode_key: str, run_id: str) -> LeaseRecord:
        """Verify ownership and atomically advance the heartbeat."""
        path = self.lease_path(episode_key)
        descriptor = self._open_current_locked(path)
        if descriptor is None:  # pragma: no cover - missing_ok is false
            raise LeaseError("episode lease does not exist")
        try:
            record = self._read_descriptor(descriptor)
            self._require_owner(record, episode_key, run_id)
            updated = self._heartbeat(record)
            atomic_write_json(path, updated.model_dump(mode="json"))
            return updated
        finally:
            os.close(descriptor)

    @contextmanager
    def mutation(self, episode_key: str, run_id: str) -> Generator[LeaseRecord]:
        """Fence one complete state mutation against recovery or another mutator."""
        self.refresh(episode_key, run_id)
        path = self.lease_path(episode_key)
        descriptor = self._open_current_locked(path)
        if descriptor is None:  # pragma: no cover - missing_ok is false
            raise LeaseError("episode lease does not exist")
        operation_error: BaseException | None = None
        try:
            record = self._read_descriptor(descriptor)
            self._require_owner(record, episode_key, run_id)
            try:
                yield record
            except BaseException as error:
                operation_error = error
                raise
            finally:
                try:
                    current = self._read_descriptor(descriptor)
                    self._require_owner(current, episode_key, run_id)
                    updated = self._heartbeat(current)
                    atomic_write_json(path, updated.model_dump(mode="json"))
                except (LeaseError, OSError) as error:
                    if operation_error is None:
                        raise LeaseError(
                            "episode lease could not be refreshed after mutation"
                        ) from error
        finally:
            os.close(descriptor)

    def release(self, episode_key: str, run_id: str) -> None:
        """Remove a lease only when the caller still owns its current inode."""
        path = self.lease_path(episode_key)
        descriptor = self._open_current_locked(path)
        if descriptor is None:  # pragma: no cover - missing_ok is false
            raise LeaseError("episode lease does not exist")
        try:
            record = self._read_descriptor(descriptor)
            self._require_owner(record, episode_key, run_id)
            try:
                path.unlink()
                sync_directory(self.locks_root)
            except OSError as error:
                raise LeaseError("episode lease could not be released") from error
        finally:
            os.close(descriptor)

    def _inspect_existing(self, path: Path, episode_key: str, now: datetime) -> LeaseRecord | None:
        descriptor = self._open_current_locked(path, missing_ok=True)
        if descriptor is None:
            return None
        try:
            record = self._read_descriptor(descriptor)
            if record.episode_key != episode_key:
                raise LeaseError("episode lease key does not match its deterministic path")
            is_stale = now - record.last_heartbeat_at > self.maximum_age
            if not is_stale and not self._owner_is_terminal(record):
                return record
            quarantine = self._quarantine_path(record, now)
            try:
                os.replace(path, quarantine)
                sync_directory(self.locks_root)
            except FileNotFoundError:
                return None
            except OSError as error:
                raise LeaseError("stale episode lease could not be quarantined") from error
            return None
        finally:
            os.close(descriptor)

    def _owner_is_terminal(self, lease: LeaseRecord) -> bool:
        profile_id, episode_date = lease.episode_key.rsplit(":", 1)
        state_path = (
            self.runtime_root / "runs" / episode_date / profile_id / lease.run_id / "state.json"
        )
        state, report = load_artifact_file("run-state", state_path)
        if not report.valid or not isinstance(state, RunState):
            return False
        return (
            state.run_id == lease.run_id
            and state.episode_key == lease.episode_key
            and state.status in {"completed", "failed", "no_op"}
        )

    def _quarantine_path(self, record: LeaseRecord, now: datetime) -> Path:
        timestamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        suffix = uuid.uuid4().hex[:8]
        return (
            self.locks_root
            / f"{self.lease_path(record.episode_key).stem}.stale-{timestamp}-{suffix}.json"
        )

    def _open_current_locked(self, path: Path, *, missing_ok: bool = False) -> int | None:
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        for _ in range(100):
            try:
                descriptor = os.open(path, flags)
            except FileNotFoundError:
                if missing_ok:
                    return None
                raise LeaseError("episode lease does not exist") from None
            except OSError as error:
                raise LeaseError("episode lease could not be opened safely") from error
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                current = os.stat(path, follow_symlinks=False)
                opened = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
                    return descriptor
            except FileNotFoundError:
                pass
            except OSError as error:
                os.close(descriptor)
                raise LeaseError("episode lease identity could not be verified") from error
            os.close(descriptor)
        raise LeaseError("episode lease identity did not stabilize")

    def _read_descriptor(self, descriptor: int) -> LeaseRecord:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            payload = os.read(descriptor, _MAX_LEASE_BYTES + 1)
            if not payload or len(payload) > _MAX_LEASE_BYTES:
                raise LeaseError("episode lease is empty or oversized")
            return LeaseRecord.model_validate_json(payload)
        except LeaseError:
            raise
        except (OSError, ValueError) as error:
            raise LeaseError("episode lease is unreadable or invalid") from error

    def _write_descriptor(self, descriptor: int, record: LeaseRecord) -> None:
        payload = record.model_dump_json(indent=2).encode("utf-8") + b"\n"
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)

    def _heartbeat(self, record: LeaseRecord) -> LeaseRecord:
        now = self._now()
        if now < record.last_heartbeat_at:
            raise LeaseError("current time precedes the recorded lease heartbeat")
        return LeaseRecord(
            contract_version=LEASE_CONTRACT_VERSION,
            run_id=record.run_id,
            episode_key=record.episode_key,
            created_at=record.created_at,
            last_heartbeat_at=now,
        )

    @staticmethod
    def _require_owner(record: LeaseRecord, episode_key: str, run_id: str) -> None:
        if record.episode_key != episode_key or record.run_id != run_id:
            raise LeaseError("episode lease is owned by another run")

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise LeaseError("lease clock must return a timezone-aware datetime")
        return now.astimezone(UTC)
