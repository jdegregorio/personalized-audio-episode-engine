"""Validate repository hygiene and durable documentation references."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

_LINK_PATTERN = re.compile(r"!?\[[^]]*]\((?P<target><[^>]+>|[^ )]+)")
_REFERENCE_LINK_PATTERN = re.compile(r"(?m)^[ ]{0,3}\[(?!\^)[^]]+]:[ \t]*(?P<target><[^>\n]+>|\S+)")
_SCRIPT_COMMAND_PATTERN = re.compile(r"uv run python (?P<path>scripts/[\w./-]+\.py)\b")
_AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".pcm", ".wav"}
_COMMAND_DOCUMENTS = {"README.md"}


def repository_paths(root: Path) -> list[str]:
    """Return tracked and visible untracked paths, excluding ignored files."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [path for path in result.stdout.split("\0") if path]


def prohibited_path_errors(paths: list[str]) -> list[str]:
    """Reject files that should never enter version control."""
    errors: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        lowered_parts = tuple(part.lower() for part in path.parts)
        if raw_path == ".env.example":
            continue
        lowered_name = path.name.lower()
        if lowered_parts and lowered_parts[0] == "runtime":
            errors.append(f"prohibited runtime artifact: {raw_path}")
        elif lowered_name == ".env" or lowered_name.startswith(".env."):
            errors.append(f"prohibited environment file: {raw_path}")
        elif lowered_name == "secrets.env" or path.suffix.lower() in {".key", ".pem"}:
            errors.append(f"prohibited credential file: {raw_path}")
        elif path.suffix.lower() in _AUDIO_SUFFIXES:
            errors.append(f"prohibited generated audio: {raw_path}")
    return errors


def markdown_errors(root: Path, paths: list[str]) -> list[str]:
    """Check lightweight style, local links, and documented script paths."""
    errors: list[str] = []
    markdown_paths = [Path(path) for path in paths if path.endswith(".md")]
    for relative_path in markdown_paths:
        document = root / relative_path
        text = document.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line != line.rstrip():
                errors.append(f"{relative_path}:{line_number}: trailing whitespace")
            if "\t" in line:
                errors.append(f"{relative_path}:{line_number}: tab character")

        link_matches = (*_LINK_PATTERN.finditer(text), *_REFERENCE_LINK_PATTERN.finditer(text))
        for match in link_matches:
            target = match.group("target").strip("<>")
            if (
                not target
                or target.startswith("#")
                or "://" in target
                or target.startswith("mailto:")
            ):
                continue
            local_target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (document.parent / local_target).resolve()
            if not resolved.is_relative_to(root.resolve()):
                errors.append(f"{relative_path}: link escapes repository: {target}")
            elif not resolved.exists():
                errors.append(f"{relative_path}: broken local link: {target}")

        if str(relative_path) in _COMMAND_DOCUMENTS or relative_path.parts[:1] == ("docs",):
            for match in _SCRIPT_COMMAND_PATTERN.finditer(text):
                command_path = root / match.group("path")
                if not command_path.is_file():
                    errors.append(
                        f"{relative_path}: documented script does not exist: {match.group('path')}"
                    )
    return errors


def check_repository(root: Path, paths: list[str] | None = None) -> list[str]:
    """Return all repository-integrity failures."""
    candidate_paths = repository_paths(root) if paths is None else paths
    return prohibited_path_errors(candidate_paths) + markdown_errors(root, candidate_paths)


def main() -> int:
    root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    errors = check_repository(Path(root_result.stdout.strip()))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("repository integrity: ok")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by smoke commands
    raise SystemExit(main())
