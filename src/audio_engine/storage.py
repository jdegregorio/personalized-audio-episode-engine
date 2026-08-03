"""Durable local-file primitives for run artifacts and state."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path


class StorageError(OSError):
    """A durable local write or hash operation failed."""


def sync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise StorageError("artifact directory could not be opened for synchronization") from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise StorageError("artifact directory could not be synchronized") from error
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Durably replace one file from a temporary sibling."""
    parent = path.parent
    if not parent.is_dir():
        raise StorageError("artifact parent directory does not exist")
    descriptor = -1
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as temporary_file:
            descriptor = -1
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        sync_directory(parent)
    except OSError as error:
        raise StorageError("artifact could not be written atomically") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    """Durably replace a UTF-8 text file."""
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def json_bytes(value: object) -> bytes:
    """Return the canonical on-disk JSON representation used by atomic writes."""
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def atomic_write_json(path: Path, value: object, *, mode: int = 0o600) -> None:
    """Durably replace a deterministic, human-readable JSON file."""
    atomic_write_bytes(path, json_bytes(value), mode=mode)


def sha256_bytes(payload: bytes) -> str:
    """Return the artifact contract's prefixed SHA-256 representation."""
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def sha256_file(path: Path) -> str:
    """Hash one file without loading it fully into memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact:
            while chunk := artifact.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise StorageError("artifact could not be hashed") from error
    return f"sha256:{digest.hexdigest()}"
