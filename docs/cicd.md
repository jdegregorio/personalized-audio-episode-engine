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

The CI workflow also checks `uv.lock`, builds the wheel and source distribution, and imports the wheel from an isolated environment rather than the editable checkout. The repository tests its integrity guard with prohibited fake paths, confirms Ruff rejects a deliberately unformatted temporary Python file, runs `scripts/check_artifacts.py` so committed schemas and synthetic fixture expectations cannot drift from their Pydantic models and semantic validators, and verifies the production skill's concise metadata, direct progressive-disclosure references, security guardrails, and documented command paths. Deterministic integration fixtures cover ordinary, shorter, optional-section, disagreement, and arbitrary-taxonomy editorial plans; balanced, imbalanced, disputed-source, arbitrary-topic, and malicious scripts; token-bounded TTS preparation; retry/resume rendering through a fake provider; real FFmpeg order/conversion/validation; and same-workspace cross-invocation recovery at every stage boundary. An executable PRD section 30 map keeps all 19 failure rows bound to stable behavior tests. The required functional smoke runs the full synthetic profile → golden agent-authored dossier/plan/script → fake speech → real MP3 → fake R2 feed → final summary path, including publication-only resume without changing audio. Ubuntu installs FFmpeg for the complete offline and smoke suites, while the Ubuntu/macOS package matrix runs the focused real audio and lease/concurrency integration subsets.

## Secret isolation

Ordinary `pull_request` and default-branch checks declare no production environment and receive no production secrets. The manually dispatched `Gemini live smoke` job runs only on `main`, uses the protected `live-smoke` environment, receives only `GEMINI_API_KEY`, and retains its synthetic PCM/WAV/metadata artifact for one day. It receives no R2 credential or setting.

The separate manually dispatched `R2 live smoke` also runs only on `main` in `live-smoke`. It receives only the bucket-scoped R2 access key/secret and the endpoint, bucket, and public-base variables. It does not receive Gemini or the feed token, publishes one random non-sensitive `probes/` text object, verifies S3/public reads and conditional-write protection, and deletes it without retaining an artifact. Neither live workflow publishes the production feed. Fork pull requests never receive live credentials. GitHub workflow logs and uploaded artifacts must contain only redacted evidence.

## Main ruleset

The repository uses one `main-minimal` ruleset. It applies to the default branch, requires a pull request with squash merge, blocks deletion and non-fast-forward pushes, requires conversation resolution, and requires the stable checks above. The solo-maintainer workflow intentionally requires zero approvals. During accelerated MVP delivery for PR 06 through PR 13, required tests, real UAT, GitHub checks, and final correctness/simplification records are the merge gate; GitHub Codex review is not requested or awaited.

Do not add overlapping rulesets, CODEOWNERS, a merge queue, deployment reviewers, or signed-commit enforcement for the MVP unless an observed failure justifies the extra mechanism.

## Failure handling

- Reproduce a failed check locally with the exact documented command.
- Fix the smallest owning defect and rerun affected local checks.
- Push the fix and wait for all required checks. PR 06 through PR 13 do not request, wait for, or act on GitHub Codex review; closed-PR feedback is triaged into a post-MVP backlog later.
- Do not bypass a red check by weakening a test or marking a required job optional.
- If a platform outage prevents a required check from completing, wait or rerun it; do not merge without evidence.
