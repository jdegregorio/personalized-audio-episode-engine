from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scripts.check_repository import (
    check_repository,
    markdown_errors,
    markdown_heading_anchors,
    prohibited_path_errors,
    repository_paths,
)

REPOSITORY_ROOT = Path(__file__).parents[2]


def test_current_repository_is_valid() -> None:
    assert check_repository(REPOSITORY_ROOT) == []


def test_repository_paths_include_visible_files() -> None:
    assert "pyproject.toml" in repository_paths(REPOSITORY_ROOT)


def test_prohibited_paths_reject_runtime_secrets_credentials_and_audio() -> None:
    paths = [
        "runtime/runs/state.json",
        ".env.local",
        ".ENV",
        ".Env.local",
        ".ENV.EXAMPLE",
        "config/secrets.env",
        "credentials/private.pem",
        "episode.mp3",
        "scripts/run-production.sh",
        "src/audio_engine/seattle_news.py",
    ]

    errors = prohibited_path_errors(paths)

    assert len(errors) == len(paths)
    assert prohibited_path_errors([".env.example", "src/audio_engine/__init__.py"]) == []


def test_markdown_errors_report_style_and_unsafe_links(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text(
        "# Test  \n\t[escape](../outside.md)\n[missing](missing.md)\n", encoding="utf-8"
    )

    errors = markdown_errors(tmp_path, ["README.md"])

    assert any("trailing whitespace" in error for error in errors)
    assert any("tab character" in error for error in errors)
    assert any("link escapes repository" in error for error in errors)
    assert any("broken local link" in error for error in errors)


def test_markdown_errors_accept_external_anchor_and_existing_links(tmp_path: Path) -> None:
    linked = tmp_path / "linked.md"
    linked.write_text("# Linked\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text(
        "# Test\n\n[anchor](#test) [external](https://example.com) [local](linked.md#linked)\n"
        "[local-ref]: linked.md#linked\n[external-ref]: https://example.com\n",
        encoding="utf-8",
    )

    assert markdown_errors(tmp_path, ["README.md", "linked.md"]) == []


def test_markdown_heading_anchors_handle_duplicates_setext_and_fences() -> None:
    text = "# Setup & usage\n# Setup & usage\nDetails\n---\n```\n# Not a heading\n```\n"

    assert markdown_heading_anchors(text) == {"setup--usage", "setup--usage-1", "details"}


def test_markdown_errors_reject_missing_same_and_cross_document_headings(
    tmp_path: Path,
) -> None:
    linked = tmp_path / "linked.md"
    linked.write_text("# Existing heading\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text(
        "# Test\n\n[local](#missing) [cross](linked.md#missing)\n", encoding="utf-8"
    )

    assert markdown_errors(tmp_path, ["README.md", "linked.md"]) == [
        "README.md: broken heading link: #missing",
        "README.md: broken heading link: linked.md#missing",
    ]


def test_markdown_errors_validate_reference_link_definitions(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text(
        "[missing][setup-doc]\n[escape][outside]\n\n"
        "[setup-doc]: docs/missing.md\n[outside]: ../outside.md\n",
        encoding="utf-8",
    )

    errors = markdown_errors(tmp_path, ["README.md"])

    assert errors == [
        "README.md: broken local link: docs/missing.md",
        "README.md: link escapes repository: ../outside.md",
    ]


def test_markdown_errors_reject_missing_documented_script(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text("```bash\nuv run python scripts/missing.py\n```\n", encoding="utf-8")

    assert markdown_errors(tmp_path, ["README.md"]) == [
        "README.md: documented script does not exist: scripts/missing.py"
    ]


def test_markdown_errors_execute_documented_script_help(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "broken.py"
    script.write_text("raise SystemExit(2)\n", encoding="utf-8")
    document = tmp_path / "README.md"
    document.write_text("uv run python scripts/broken.py\n", encoding="utf-8")

    assert markdown_errors(tmp_path, ["README.md", "scripts/broken.py"]) == [
        "documented command --help failed (2): uv run python scripts/broken.py --help"
    ]


def test_ruff_rejects_a_deliberately_unformatted_change(tmp_path: Path) -> None:
    ruff = shutil.which("ruff")
    assert ruff is not None
    bad_file = tmp_path / "unformatted.py"
    bad_file.write_text("value=  1\n", encoding="utf-8")

    result = subprocess.run(
        [ruff, "format", "--check", str(bad_file)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
