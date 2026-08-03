# Project agent instructions

Before changing this repository, read and follow:

- [`prd.md`](prd.md) for product and technical requirements.
- [`plan.md`](plan.md) for the approved MVP sequence and per-PR scope.
- [`CONTRIBUTORS.md`](CONTRIBUTORS.md) for the mandatory worktree, SDLC, testing, documentation, review, and merge process.

Use a fresh worktree and `feature/` branch for every PR. Keep changes within the declared scope and update affected documentation in the same PR.

Never merge before at least one configured GitHub Codex review round completes. Use at most two Codex review rounds per PR: the initial review and, when useful, one rereview after changes. Examine every finding, then implement it, dismiss it with concrete rationale, or defer valid non-blocking work to an explicit owning item in `plan.md`; record the disposition and resolve the thread. After round two, do not request another Codex review. Re-run affected checks and perform final correctness and simplification reviews for any later changes.

Do not skip or weaken required testing, smoke, UAT, or review when tooling or an environment is initially unavailable. Diagnose and independently repair in-scope blockers when access and authority permit, rerun the required evidence, and continue without asking the owner. Stop only when progress genuinely requires owner-only secrets, account/billing or permission changes, physical-device setup, or another action the agent cannot perform; state the exact prerequisite instead of substituting a weaker test.

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
