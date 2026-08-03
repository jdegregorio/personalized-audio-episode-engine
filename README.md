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

Run the complete local gate:

```bash
uv run python scripts/check_repository.py
uv run python scripts/check_artifacts.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m "not live and not smoke" --cov=audio_engine --cov=scripts --cov-report=term-missing --cov-fail-under=85
uv run pytest -m "smoke and not live"
```

See [`docs/setup.md`](docs/setup.md) for workstation, account, and secret setup. Contributors must follow [`CONTRIBUTORS.md`](CONTRIBUTORS.md), including its worktree, review, evidence, and merge gates.

Validate the prepared host without contacting Gemini or R2:

```bash
uv run python scripts/doctor.py --profile examples/profiles/world-us-seattle-news.yaml
```

Episode profiles are strict, versioned YAML data. See [`docs/profile-authoring.md`](docs/profile-authoring.md) and the committed [`schemas/episode-profile-v1.0.schema.json`](schemas/episode-profile-v1.0.schema.json).

Validate a persisted pipeline artifact without modifying it:

```bash
uv run python scripts/validate_artifact.py --type evidence --input tests/fixtures/artifacts/valid/evidence-dossier.json
```

The supported artifact types, versioning policy, evidence lineage, safe locators, and optional full-report output are documented in [`docs/artifact-contracts.md`](docs/artifact-contracts.md).

After loading the owner-managed environment, initialize one owner-checked local run:

```bash
uv run python scripts/init_run.py \
  --profile examples/profiles/world-us-seattle-news.yaml
```

The run layout, lifecycle stages, invalidation, same-episode no-op behavior, and stale-lease recovery are documented in [`docs/run-lifecycle.md`](docs/run-lifecycle.md).

## Security boundary

The MVP feed contains public-news content but uses an unguessable URL. That URL is access material, not authentication. Never commit or paste credentials, tokenized object keys, runtime data, or complete feed URLs. Profiles containing personal or otherwise sensitive information are outside the MVP and require a separate authenticated or encrypted publication design.
