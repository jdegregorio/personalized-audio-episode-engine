"""Validate repository hygiene and durable documentation references."""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

_LINK_PATTERN = re.compile(r"!?\[[^]]*]\((?P<target><[^>]+>|[^ )]+)")
_REFERENCE_LINK_PATTERN = re.compile(r"(?m)^[ ]{0,3}\[(?!\^)[^]]+]:[ \t]*(?P<target><[^>\n]+>|\S+)")
_SCRIPT_COMMAND_PATTERN = re.compile(r"uv run python (?P<path>scripts/[\w./-]+\.py)\b")
_ATX_HEADING_PATTERN = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(?P<heading>.*?))?[ \t]*$")
_SETEXT_HEADING_PATTERN = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_FENCE_PATTERN = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
_AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".pcm", ".wav"}
_SHELL_SUFFIXES = {".bash", ".sh", ".zsh"}
_TOPIC_MODULE_PATTERN = re.compile(
    r"(?:^|[-_])(marine|news|seattle|world(?:[-_]us)?)(?:[-_]|$)", re.IGNORECASE
)
_COMMAND_DOCUMENTS = {"CONTRIBUTORS.md", "README.md"}


def markdown_heading_anchors(text: str) -> set[str]:
    """Return GitHub-style anchors for ATX and setext headings outside code fences."""
    anchors: set[str] = set()
    fence_character: str | None = None
    fence_length = 0
    lines = text.splitlines()
    index = 0

    def add_anchor(heading: str) -> None:
        without_tags = re.sub(r"<[^>]+>", "", html.unescape(heading))
        slug = re.sub(r"[^\w\s-]", "", without_tags.lower())
        slug = re.sub(r"\s", "-", slug).strip("-")
        if not slug:
            return
        candidate = slug
        suffix = 0
        while candidate in anchors:
            suffix += 1
            candidate = f"{slug}-{suffix}"
        anchors.add(candidate)

    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        if fence_character is not None:
            if stripped.startswith(fence_character * fence_length):
                fence_character = None
                fence_length = 0
            index += 1
            continue

        fence_match = _FENCE_PATTERN.match(line)
        if fence_match:
            fence = fence_match.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            index += 1
            continue

        atx_match = _ATX_HEADING_PATTERN.match(line)
        if atx_match:
            heading = atx_match.group("heading") or ""
            add_anchor(re.sub(r"[ \t]+#+[ \t]*$", "", heading))
            index += 1
            continue

        if (
            line.strip()
            and index + 1 < len(lines)
            and _SETEXT_HEADING_PATTERN.match(lines[index + 1])
        ):
            add_anchor(line.strip())
            index += 2
            continue

        index += 1

    return anchors


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
        elif path.suffix.lower() in _SHELL_SUFFIXES:
            errors.append(f"prohibited undocumented production shell command: {raw_path}")
        elif (
            lowered_parts[:2] == ("src", "audio_engine")
            and path.suffix.lower() == ".py"
            and _TOPIC_MODULE_PATTERN.search(path.stem)
        ):
            errors.append(f"prohibited topic-specific engine module: {raw_path}")
    return errors


def markdown_errors(root: Path, paths: list[str]) -> list[str]:
    """Check lightweight style, local links, and documented script paths."""
    errors: list[str] = []
    documented_scripts: set[str] = set()
    anchor_cache: dict[Path, set[str]] = {}
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
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            local_target, separator, raw_fragment = target.partition("#")
            local_target = unquote(local_target.split("?", 1)[0])
            resolved = (
                (document.parent / local_target).resolve() if local_target else document.resolve()
            )
            if not resolved.is_relative_to(root.resolve()):
                errors.append(f"{relative_path}: link escapes repository: {target}")
            elif not resolved.exists():
                errors.append(f"{relative_path}: broken local link: {target}")
            elif separator and raw_fragment and resolved.suffix.lower() == ".md":
                anchors = anchor_cache.get(resolved)
                if anchors is None:
                    anchors = markdown_heading_anchors(resolved.read_text(encoding="utf-8"))
                    anchor_cache[resolved] = anchors
                if unquote(raw_fragment) not in anchors:
                    errors.append(f"{relative_path}: broken heading link: {target}")

        if str(relative_path) in _COMMAND_DOCUMENTS or relative_path.parts[:1] == ("docs",):
            for match in _SCRIPT_COMMAND_PATTERN.finditer(text):
                relative_command_path = match.group("path")
                command_path = root / relative_command_path
                if not command_path.is_file():
                    errors.append(
                        f"{relative_path}: documented script does not exist: "
                        f"{relative_command_path}"
                    )
                else:
                    documented_scripts.add(relative_command_path)

    for command_path in sorted(documented_scripts):
        command = ["uv", "run", "python", command_path, "--help"]
        try:
            result = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            errors.append(f"documented command could not run: {' '.join(command)}: {error}")
        else:
            if result.returncode != 0:
                errors.append(
                    f"documented command --help failed ({result.returncode}): {' '.join(command)}"
                )
    return errors


def check_repository(root: Path, paths: list[str] | None = None) -> list[str]:
    """Return all repository-integrity failures."""
    candidate_paths = repository_paths(root) if paths is None else paths
    return prohibited_path_errors(candidate_paths) + markdown_errors(root, candidate_paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
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
