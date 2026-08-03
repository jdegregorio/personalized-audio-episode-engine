from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
SCHEDULED_TASK = ROOT / "docs/scheduled-task.md"
WORKFLOW = ROOT / ".github/workflows/release-candidate.yml"


def _canonical_prompt(document: str) -> str:
    match = re.search(
        r"<!-- scheduled-task-prompt:start -->\s*```text\n(?P<prompt>.*?)\n```\s*"
        r"<!-- scheduled-task-prompt:end -->",
        document,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group("prompt")


def test_scheduled_prompt_covers_production_contract() -> None:
    document = SCHEDULED_TASK.read_text(encoding="utf-8")
    prompt = _canonical_prompt(document)

    required_prompt_text = (
        "$produce-audio-episode",
        "examples/profiles/world-us-seattle-news.yaml",
        "America/Los_Angeles",
        "native\nweb research",
        "repository's schemas, prompts, documented commands",
        "/Users/jdegregorio/.config/personalized-audio-episode-engine/secrets.env",
        "printing its values or copying it into the checkout",
        "Do not modify application source code, dependencies, schemas, profile\nconfiguration",
        "Resume an\nincomplete run for the same profile and date",
        "required validations and audio checks",
        "terminal finalization",
        "final\nhuman-readable run summary",
    )
    assert all(value in prompt for value in required_prompt_text)

    required_task_text = (
        "new independent context",
        "Local project, workspace-write access, network enabled",
        "Daily at 07:00 in `America/Los_Angeles`",
        "GPT-5.6 Sol",
        "three consecutive scheduled dates",
        "does not count as one of the three",
    )
    assert all(value in document for value in required_task_text)
    assert (ROOT / "examples/profiles/world-us-seattle-news.yaml").is_file()
    assert (ROOT / ".agents/skills/produce-audio-episode/SKILL.md").is_file()


def test_release_candidate_workflow_is_manual_secret_free_and_complete() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)

    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in workflow_text
    assert "environment:" not in workflow_text

    required_commands = (
        "uv sync --locked --all-extras --dev",
        "uv lock --check",
        "scripts/check_repository.py",
        "scripts/check_artifacts.py",
        "ruff format --check",
        "ruff check",
        "pyright",
        'pytest -m "not live and not smoke"',
        'pytest -m "smoke and not live"',
        "--cov-fail-under=85",
        "uv build",
        "actions/upload-artifact@v4",
    )
    assert all(command in workflow_text for command in required_commands)
