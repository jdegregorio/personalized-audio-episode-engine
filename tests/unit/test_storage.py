from __future__ import annotations

import os
from pathlib import Path

import pytest

from audio_engine.storage import (
    StorageError,
    atomic_write_bytes,
    atomic_write_json,
    sha256_bytes,
    sha256_file,
)


def test_atomic_write_replaces_content_and_applies_private_mode(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text("old", encoding="utf-8")

    atomic_write_json(path, {"value": "new"})

    assert path.read_text(encoding="utf-8") == '{\n  "value": "new"\n}\n'
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".artifact.json.*.tmp"))


def test_atomic_replace_failure_preserves_previous_file_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(b"previous")

    def fail_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        del source, destination
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(StorageError, match="atomically"):
        atomic_write_bytes(path, b"replacement")

    assert path.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_hashes_use_contract_prefix_and_file_bytes(tmp_path: Path) -> None:
    payload = b"synthetic artifact bytes"
    path = tmp_path / "artifact.bin"
    path.write_bytes(payload)

    assert sha256_file(path) == sha256_bytes(payload)
    assert sha256_file(path).startswith("sha256:")
    assert len(sha256_file(path)) == len("sha256:") + 64


def test_atomic_write_requires_existing_parent(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="parent"):
        atomic_write_bytes(tmp_path / "missing" / "artifact.json", b"data")
