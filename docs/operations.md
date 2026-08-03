# Operations

The engine is currently in the repository-foundation phase. Offline development is supported; production generation and publication are introduced and accepted only by their owning PRs in [`plan.md`](../plan.md).

## Development gate

Run from the active feature worktree:

```bash
uv sync --locked --all-extras --dev
uv lock --check
uv build
uv run python scripts/check_repository.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m "not live and not smoke" --cov=audio_engine --cov=scripts --cov-report=term-missing --cov-fail-under=85
uv run pytest -m smoke
```

The `not live and not smoke` suite is deterministic and must not read the owner's real environment file or access a network service. Smoke tests prove user-visible behavior at the smallest useful boundary. Live tests remain explicit and use the narrow `live-smoke` environment only after their implementation PR.

## Production invariants

- One independent Codex run processes one profile.
- Files are the system of record; a stage advances only after durable validation.
- Use only documented repository commands. A production run never writes ad hoc source code.
- Production runs do not modify tracked code, dependencies, schemas, profiles, or documentation.
- Resume valid work rather than rerunning successful external operations.
- Never log credentials, tokenized object keys, or complete feed URLs.
- Default CI cannot synthesize speech or publish objects because it receives no production secrets.

## Rollback at this phase

PR 01 adds no production runtime. Revert its squash commit to remove the foundation. If CI configuration itself prevents safe progress, temporarily disable only the affected required-check rule, repair it in a PR, and restore the rule immediately after the check is available. Do not weaken the pull-request, deletion, or non-fast-forward protections.

Service-specific recovery and rotation are documented in [`cloudflare-r2.md`](cloudflare-r2.md) and will be expanded alongside their implementations.
