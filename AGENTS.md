# Project agent instructions

Before changing this repository, read and follow:

- [`prd.md`](prd.md) for product and technical requirements.
- [`plan.md`](plan.md) for the approved MVP sequence and per-PR scope.
- [`CONTRIBUTORS.md`](CONTRIBUTORS.md) for the mandatory worktree, SDLC, testing, documentation, review, and merge process.

Use a fresh worktree and `feature/` branch for every PR. Keep changes within the declared scope and update affected documentation in the same PR.

Never merge a PR before the configured Codex auto-review has completed and every review comment has been implemented and resolved, or answered with a concrete rationale and explicitly resolved or dismissed. Re-run affected checks and review after changes so the final commit is covered.

## Production workflow constraints

- Use `uv` for Python environments, dependency locking, and command execution.
- Use only the documented `uv run python scripts/...` commands for repeatable deterministic work. Do not create ad hoc production scripts during an episode run.
- Treat persisted run artifacts as authoritative; validate every structured artifact before advancing a stage.
- Keep schemas, Python code, and workflow instructions topic-generic. Source-specific policy belongs in a profile or independently maintained capability.
- Use an available research capability when it satisfies the profile, otherwise use native research when the profile permits it.
- Record repairs and retries in run state, and resume validated stages instead of repeating them.
- Never commit credentials, private feed URLs, generated audio, or runtime artifacts.
- A scheduled production run must not modify application code, dependencies, schemas, profiles, or tracked documentation.
- Update every affected setup, architecture, operations, reference, security, and troubleshooting document in the same pull request as a behavior or configuration change.
