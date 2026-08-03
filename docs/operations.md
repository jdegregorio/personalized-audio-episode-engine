# Operations

The engine currently supports validated environment configuration, topic-generic profile preflight, and deterministic artifact/lineage validation. Run creation and production behavior are introduced only by their owning PRs in [`plan.md`](../plan.md).

## Development gate

Run from the active feature worktree:

```bash
uv sync --locked --all-extras --dev
uv lock --check
uv build
artifact_venv="$(mktemp -d)/venv"
uv venv --python 3.12 "${artifact_venv}"
uv pip install --python "${artifact_venv}/bin/python" dist/*.whl
"${artifact_venv}/bin/python" -c "import audio_engine; print(audio_engine.__version__)"
uv run python scripts/check_repository.py
uv run python scripts/check_artifacts.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m "not live and not smoke" --cov=audio_engine --cov=scripts --cov-report=term-missing --cov-fail-under=85
uv run pytest -m "smoke and not live"
```

The `not live and not smoke` suite is deterministic and must not read the owner's real environment file or access a network service. Smoke tests prove user-visible behavior at the smallest useful boundary. Live tests remain explicit and use the narrow `live-smoke` environment only after their implementation PR.

## Environment preflight

Load the owner-managed environment as described in [`setup.md`](setup.md), then run:

```bash
uv run python scripts/doctor.py --profile examples/profiles/world-us-seattle-news.yaml
```

`PASS` means local configuration and tools are structurally ready; it is not a live Gemini or R2 probe. A `FAIL` line names the setting, tool, root, profile, or required capability the operator must fix without echoing its value.

## Artifact validation

Validate one JSON artifact through the public contract boundary:

```bash
uv run python scripts/validate_artifact.py --type evidence --input <artifact-path>
```

Fatal validation writes a concise JSON result to stderr and exits non-zero. Pass `--report <report-path>` to persist the complete validation result for a repair; the report path may not overwrite the input. Filesystem source locators require one or more explicit `--allowed-input-root <path>` arguments. See [`artifact-contracts.md`](artifact-contracts.md) for supported types and the boundary between structural validation and later phase policy.

## Production invariants

- One independent Codex run processes one profile.
- Files are the system of record; a stage advances only after durable validation.
- Use only documented repository commands. A production run never writes ad hoc source code.
- Production runs do not modify tracked code, dependencies, schemas, profiles, or documentation.
- Resume valid work rather than rerunning successful external operations.
- Never log credentials, tokenized object keys, or complete feed URLs.
- Default CI cannot synthesize speech or publish objects because it receives no production secrets.

## Rollback at this phase

No doctor or artifact validator uploads data or creates a run. Revert the PR 03 squash commit to remove artifact contracts while retaining PR 02 configuration/profile support. Invalid generated artifacts are repaired at their owning stage; do not bypass version, lineage, locator, or evidence validation.

Service-specific recovery and rotation are documented in [`cloudflare-r2.md`](cloudflare-r2.md) and will be expanded alongside their implementations.
