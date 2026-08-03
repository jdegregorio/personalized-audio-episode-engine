# Contributor and SDLC guidelines

These rules apply to every human or automated contributor. The product requirements live in [`prd.md`](prd.md), and the ordered MVP implementation scope lives in [`plan.md`](plan.md). This file is the canonical delivery, review, and merge contract.

## Worktrees and branch order

Every pull request must be developed in a new sibling Git worktree on a new `feature/` branch created from the latest `origin/main`. Do not implement feature changes in the primary checkout, reuse a prior PR worktree, or start a dependent implementation PR before its predecessor and post-merge checks pass.

```bash
git fetch origin
git worktree add ../paee-pr-<NN>-<slug> \
  -b feature/pr-<NN>-<slug> origin/main
cd ../paee-pr-<NN>-<slug>
```

After merge, update the primary checkout, run required post-merge checks, and remove the completed worktree. Scheduled production runs use the stable primary checkout, not an implementation worktree.

## Pull-request scope and evidence

Keep each PR within its declared scope. Its description must include:

- Objective and linked PRD requirements or acceptance criteria.
- In-scope behavior and explicit non-goals.
- Risk and security/privacy impact.
- Local test commands and results.
- GitHub Actions results.
- Functional smoke and reviewer-facing UAT procedure and evidence.
- Documentation impact, including exact files reviewed or changed.
- Simplification review and rationale for retained complexity.
- Rollback approach.
- New dependencies, configuration, schema, or operational changes.

Do not commit secrets, private URLs, runtime data, generated audio, or production evidence. Use concise redacted PR comments or short-lived CI artifacts.

## Automated feedback loops

Run the applicable local gate before review. Once PR 01 introduces the project tooling, the complete gate is:

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

Also run `doctor.py` and the offline vertical slice once their owning PRs introduce them. Tests use temporary roots, fake tokens, mocked network providers, and deterministic fixtures; default tests must not read a developer's real environment file or call live services.

Default GitHub Actions must be secret-free and cover repository/document integrity, Markdown links and documented commands, package build/import, Ruff, Pyright, unit/contract/integration tests, offline functional smoke, Python 3.12 portability, dependency review, and CodeQL. Required jobs fail closed. Live Gemini or R2 probes are explicit local or `main`-restricted jobs and receive only the secrets they need.

## Unblocking work without weakening evidence

Required test, smoke, UAT, correctness-review, and simplification-review evidence is never skipped because a tool, dependency, environment, or service is initially unavailable. Contributors must diagnose the failure and independently apply the smallest safe in-scope repair when they have the access and authority to do so, then rerun the affected gate and continue the PR without waiting for owner approval.

Stop and request owner help only when the remaining blocker genuinely requires an action the contributor cannot perform, such as providing or rotating a secret, completing account or billing setup, approving an external permission, configuring a physical device, or making an unavailable owner-only product choice. Report the exact missing prerequisite and do not substitute mocks, reduce coverage, waive a gate, or proceed to dependent PRs while required evidence remains incomplete.

## Test and acceptance layers

Each PR supplies the layers applicable to its behavior:

- **Unit tests:** isolated success, boundary, and failure behavior.
- **Contract/integration tests:** artifact relationships, provider boundaries, filesystem effects, and concurrency.
- **Functional smoke:** the smallest documented runnable path that proves expected output, not merely an import or zero exit code.
- **UAT:** copy-pasteable steps that inspect the user-visible result. Use synthetic inputs early and real Codex research, Gemini, R2, AntennaPod, or scheduling only in the owning PR.

Maintain at least 85% line coverage for deterministic Python code unless a PR explains an exception. Directly test safety-critical state, locks, paths/object keys, idempotency, publication ordering, conditional writes, and recovery. Network access is blocked or mocked by default.

## Correctness and simplification reviews

Every PR receives distinct correctness and simplification passes against the final reviewed commit. The simplification pass inspects the complete diff and asks whether the same compliant behavior can use fewer lines, files, dependencies, abstractions, configuration switches, or public interfaces without sacrificing correctness, validation, security, tests, readability, or maintainability.

At minimum, inspect:

```bash
git diff --stat origin/main...HEAD
git diff --numstat origin/main...HEAD
git diff origin/main...HEAD
```

Reject unrelated churn, speculative frameworks, duplicated or overly nested logic, clever compression, dead paths, and documentation that creates multiple conflicting sources of truth. Record the reviewer, commit SHA, simplifications made, justified retained complexity, and a final pass or changes-requested decision. Any subsequent change invalidates that reviewed SHA and requires affected checks and review to run again.

## GitHub Codex feedback during accelerated MVP delivery

For PR 06 through PR 13, do not request or wait for GitHub Codex auto-review and do not change the active PR in response to it. A review that is absent, pending, in progress, or incomplete is not a merge blocker. Required GitHub checks, local correctness and simplification passes, applicable tests, smoke, and real UAT remain merge gates.

Merge as soon as those gates pass. Feedback left on a PR before or after merge is intentionally outside the active delivery loop; scrape closed PRs later into a separate post-MVP backlog. If repository settings require conversation resolution to merge, resolve the thread administratively without treating it as an implementation gate, while preserving the closed PR as the source for later backlog triage.

## Documentation and release discipline

Documentation is part of each implementation. Update affected setup, architecture, commands, schemas, operations, troubleshooting, security, skill references, and, once PR 01 introduces it, `docs/implementation-status.md` in the same PR. Do not defer known documentation work.

Every merge to `main` reruns the full offline suite. Dependency changes update `uv.lock` and justify the dependency. Schema changes are additive within a version or deliberately versioned with compatibility tests. Production activation and live smoke are explicit operator actions; default CI never publishes the feed or mutates production runtime state.

## Definition of done

A PR is complete only when:

- Its scoped requirements and acceptance criteria pass.
- Affected documentation matches the implementation.
- Applicable local, CI, smoke, UAT, failure, and recovery checks pass.
- Correctness and simplification reviews cover the final SHA; no GitHub Codex review is required for PR 06 through PR 13.
- No secret, runtime artifact, live-news dependency, source-specific client, unrelated refactor, or deferred documentation is included.
- The branch is current with its merged predecessor and is safe to squash-merge.
