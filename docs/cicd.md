# Continuous integration and delivery controls

GitHub Actions mirrors the local commands in [`operations.md`](operations.md). All pull-request jobs are deterministic and secret-free.

## Stable checks

The required workflow surface is deliberately small:

| Check | Responsibility |
| --- | --- |
| `Repository integrity` | Secret/runtime path policy, Markdown/local-command checks, generated-schema drift, and valid/invalid golden artifact fixtures |
| `Lint and type check` | Ruff formatting/lint and strict Pyright |
| `Offline tests` | Unit/contract/integration tests with at least 85% deterministic Python line coverage |
| `Functional smoke` | Smallest documented runnable behavior using synthetic inputs |
| `Package build (ubuntu)` | Locked Python 3.12 build and import on Ubuntu |
| `Package build (macos)` | Locked Python 3.12 build and import on macOS |
| `Dependency review` | Pull-request dependency risk review |
| `CodeQL (python)` | Python static security analysis |

The CI workflow also checks `uv.lock`, builds the wheel and source distribution, and imports the wheel from an isolated environment rather than the editable checkout. The repository tests its integrity guard with prohibited fake paths, confirms Ruff rejects a deliberately unformatted temporary Python file, and runs `scripts/check_artifacts.py` so committed schemas and synthetic fixture expectations cannot drift from their Pydantic models and semantic validators.

## Secret isolation

Ordinary `pull_request` and default-branch checks declare no production environment and receive no production secrets. Explicit live jobs added in later PRs must use the `live-smoke` environment, run only on `main` or by protected manual dispatch, and request only service-specific values. Fork pull requests never receive live credentials. GitHub workflow logs and uploaded artifacts must contain only redacted evidence.

## Main ruleset

The repository uses one `main-minimal` ruleset. It applies to the default branch, requires a pull request with squash merge, blocks deletion and non-fast-forward pushes, requires conversation resolution, and requires the stable checks above. The solo-maintainer workflow intentionally requires zero approvals; the mandatory correctness, simplification, and Codex auto-review records in [`CONTRIBUTORS.md`](../CONTRIBUTORS.md) remain the review gate.

Do not add overlapping rulesets, CODEOWNERS, a merge queue, deployment reviewers, or signed-commit enforcement for the MVP unless an observed failure justifies the extra mechanism.

## Failure handling

- Reproduce a failed check locally with the exact documented command.
- Fix the smallest owning defect and rerun affected local checks.
- Push the fix and wait for all required checks. Request at most one Codex rereview after the initial round.
- If round two causes changes, disposition its findings, rerun affected checks and final correctness/simplification reviews, and do not request a third Codex review.
- Do not bypass a red check by weakening a test or marking a required job optional.
- If a platform outage prevents a required check from completing, wait or rerun it; do not merge without evidence.
