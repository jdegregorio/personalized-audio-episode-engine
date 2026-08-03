# Personalized Audio Episode Engine

This repository will contain a profile-driven workflow that turns source-grounded research into a two-host audio episode and publishes it to a private-by-secret-link podcast feed. The approved MVP is intentionally one vertical slice: Codex supplies editorial judgment, while small Python scripts provide deterministic validation, state, audio, and publication operations.

Implementation follows the ordered pull requests in [`plan.md`](plan.md). The current delivery status is recorded in [`docs/implementation-status.md`](docs/implementation-status.md).

## Development setup

The supported development runtime is Python 3.12 on macOS or Ubuntu, managed by `uv`.

```bash
uv sync --locked --all-extras --dev
uv lock --check
uv build
artifact_venv="$(mktemp -d)/venv"
uv venv --python 3.12 "${artifact_venv}"
uv pip install --python "${artifact_venv}/bin/python" dist/*.whl
"${artifact_venv}/bin/python" -c "import audio_engine; print(audio_engine.__version__)"
```

Run the complete PR 01 local gate:

```bash
uv run python scripts/check_repository.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m "not live and not smoke" --cov=audio_engine --cov=scripts --cov-report=term-missing --cov-fail-under=85
uv run pytest -m "smoke and not live"
```

See [`docs/setup.md`](docs/setup.md) for workstation, account, and secret setup. Contributors must follow [`CONTRIBUTORS.md`](CONTRIBUTORS.md), including its worktree, review, evidence, and merge gates.

## Security boundary

The MVP feed contains public-news content but uses an unguessable URL. That URL is access material, not authentication. Never commit or paste credentials, tokenized object keys, runtime data, or complete feed URLs. Profiles containing personal or otherwise sensitive information are outside the MVP and require a separate authenticated or encrypted publication design.
