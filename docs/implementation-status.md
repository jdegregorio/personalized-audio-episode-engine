# Implementation status

The approved scope and sequence live in [`plan.md`](../plan.md). This page records delivered behavior without redefining requirements.

| PR | Capability | Status |
| --- | --- | --- |
| 01 | Repository foundation and delivery guardrails | Implemented on `feature/pr-01-foundation`; pending review and merge |
| 02 | Configuration, profile loading, path safety, and doctor | Not started |
| 03 | Artifact contracts, validators, and fixtures | Not started |
| 04 | Run lifecycle, state, leases, and invalidation | Not started |
| 05 | Capability-aware collection skill | Not started |
| 06 | Editorial planning | Not started |
| 07 | Grounded two-host scripting | Not started |
| 08 | TTS preparation | Not started |
| 09 | Gemini rendering and voice selection | Not started |
| 10 | Audio assembly | Not started |
| 11 | Cloudflare R2 publication | Not started |
| 12 | Complete offline vertical slice | Not started |
| 13 | Scheduled execution and release qualification | Not started |

## PR 01 delivered surface

- Python 3.12 `src` package and `uv` lock boundary.
- Ruff, strict Pyright, pytest markers, coverage, isolated wheel import, integrity, portability, dependency-review, and CodeQL feedback.
- Credential-free environment template and repository/runtime ignore policy.
- Worktree-safe setup, Cloudflare bootstrap, CI, operations, and security-boundary documentation.
- Pull-request evidence template and preserved contributor/Codex review gates.

Product schemas, workflow state, research, speech, audio processing, publication, and scheduling remain deliberately unavailable until their ordered implementation PRs.
