# Implementation status

The approved scope and sequence live in [`plan.md`](../plan.md). This page records delivered behavior without redefining requirements.

| PR | Capability | Status |
| --- | --- | --- |
| 01 | Repository foundation and delivery guardrails | Implemented on `main` |
| 02 | Configuration, profile loading, path safety, and doctor | Implemented on `main` |
| 03 | Artifact contracts, validators, and fixtures | Implemented on `main` |
| 04 | Run lifecycle, state, leases, and invalidation | Implemented on `main` |
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
- Pull-request evidence template and the canonical one-or-two-round Codex review/disposition gate.

Workflow mutation, research, speech, audio processing, publication behavior, and scheduling remain deliberately unavailable until their ordered implementation PRs.

## PR 02 delivered surface

- Strict Pydantic/YAML episode-profile contract with explicit schema version `1.0` and a matching committed JSON Schema.
- Topic-specific world/U.S./Seattle example data plus contract coverage for an unrelated topic and arbitrary section identifiers.
- Typed environment settings, timezone-aware episode dates, root/symlink safety, fixed R2 key construction, and secret/location redaction helpers.
- Non-networking `doctor.py` checks for the local toolchain, locked dependencies, settings, writable roots, profile validity, publication references, and detectable required capabilities.

## PR 03 delivered surface

- Strict contract version `1.0` Pydantic models and matching JSON Schemas for collection request, evidence dossier, editorial plan, episode script, published episode, and run state.
- Topic-generic evidence candidates, claims, supports, public-web/connector/filesystem locator policy, provenance timestamps, independence groups, prompt versions, and artifact references.
- Deterministic evidence referential validation plus baseline plan/script lineage hooks; phase-specific editorial and prose policy remains in PRs 06–07.
- Public read-only artifact validation with concise JSON errors, exact JSON-pointer paths, optional full reports, and no input mutation.
- Synthetic valid, invalid, prompt-injection, and RSS golden fixtures enforced by permanent repository-integrity CI.

## PR 04 delivered surface

- Canonical episode keys and unique run IDs with the date/profile/run filesystem layout, private atomic writes, SHA-256 references, and additive run provenance.
- An owner-checked initialization command that creates a validated collection request, durable state, and one-screen summary only after exclusive episode ownership.
- Heartbeat leases with live-owner no-op behavior, mutation-wide owner fencing, owner-only refresh/release, terminal and stale recovery, fail-closed corruption handling, atomic stale quarantine, and portable retry of the transient zero-byte `O_EXCL` creation window.
- Validated stage transitions, current-state identity/upstream-reference binding, and exact hash-based downstream invalidation for profile, request, dossier, plan, and script changes.
- Process concurrency, stale-race, mutation-safety, recovery, secret-redaction, and public-command smoke coverage using temporary local roots.
