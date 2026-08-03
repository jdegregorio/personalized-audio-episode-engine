# Implementation status

The approved scope and sequence live in [`plan.md`](../plan.md). This page records delivered behavior without redefining requirements.

| PR | Capability | Status |
| --- | --- | --- |
| 01 | Repository foundation and delivery guardrails | Implemented on `main` |
| 02 | Configuration, profile loading, path safety, and doctor | Implemented on `main` |
| 03 | Artifact contracts, validators, and fixtures | Implemented on `main` |
| 04 | Run lifecycle, state, leases, and invalidation | Implemented on `main` |
| 05 | Capability-aware collection skill | Implemented on `main` |
| 06 | Editorial planning | Implemented on `main` |
| 07 | Grounded two-host scripting | Implemented on `main` |
| 08 | TTS preparation | Implemented on `main` |
| 09 | Gemini rendering and voice selection | Implemented on `main` |
| 10 | Audio assembly | Implemented on `main` |
| 11 | Cloudflare R2 publication | Implemented on `main` |
| 12 | Complete offline vertical slice | Implemented in PR 12 |
| 13 | Scheduled execution and release qualification | Not started |

## PR 01 delivered surface

- Python 3.12 `src` package and `uv` lock boundary.
- Ruff, strict Pyright, pytest markers, coverage, isolated wheel import, integrity, portability, dependency-review, and CodeQL feedback.
- Credential-free environment template and repository/runtime ignore policy.
- Worktree-safe setup, Cloudflare bootstrap, CI, operations, and security-boundary documentation.
- Pull-request evidence template plus correctness and simplification review records; the current accelerated-MVP review policy is in `CONTRIBUTORS.md`.

Later workflow capabilities remain deliberately unavailable until their ordered implementation PRs.

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

## PR 05 delivered surface

- A concise `produce-audio-episode` skill with stage routing and focused workflow, collection, and run-state references.
- Capability-aware selection from already available suitable tools, native public-web fallback, optional-capability failover, and actionable required-capability failure without automatic installation.
- One method-neutral dossier recorder that binds request lineage/method/prompt/limits, persists validation outcomes, allows one repair, fails after attempt two, surfaces warnings, and resumes verified evidence without recollection.
- Topic-generic native/specialized adapter coverage, prompt-injection guardrails, optional-collector guidance, and collection troubleshooting without source-specific clients.

## PR 06 delivered surface

- A focused editorial skill reference and one distinct Codex phase that consumes the complete profile and validated dossier without a scoring/ranking engine or second model.
- One recorder that binds prompt and input hashes, validates complete selected/excluded dispositions plus profile-owned sections, hosts, reason codes, bounds, and disagreement notes, and advances only valid plans.
- Durable plan validation reports, one repair, terminal exhaustion, verified resume, and hash-based invalidation when accepted dossier or plan bytes change.
- Ordinary, shorter-useful, optional-empty-section, source-disagreement, and arbitrary non-news golden-plan coverage.

## PR 07 delivered surface

- A distinct scriptwriting skill phase that consumes the complete profile, dossier, and plan without a fact-check model, scoring engine, or provider integration.
- Deterministic validation for plan/candidate/claim/support/source lineage, required attribution and qualifications, disagreement, exactly two configured speakers/voices, spoken-text safety, duration, and TTS limits.
- Machine-readable conversational warnings for host balance, consecutive/reaction turns, performance cues, stock phrases, missing takeaways, and preferred-duration misses, with optional profile-owned fatal promotion.
- Durable script validation reports, one repair, terminal exhaustion, verified resume, downstream invalidation, and exact transcript projection with recorded hashes.
- Balanced, imbalanced, disputed-source, arbitrary-topic, and malicious-text golden coverage plus fixture end-to-end smoke through the `tts` stage.

## PR 08 delivered surface

- One provider-neutral renderer protocol plus an explicit capability record for the configured Gemini preview model; preparation performs no network call.
- Conservative complete-prompt token estimation with the profile's 7,000-token safe limit and the model's 8,192-token absolute limit enforced before every emitted request.
- Deterministic natural-boundary packing toward two-to-four-minute segments, with mid-discussion splitting only when required and fail-closed oversized turns.
- Versioned manifest and atomic structured prompts containing stable hosts/voices/descriptions, scene, direction, position, minimal continuity, and exact transcript in separate fields.
- Durable preparation hashes/state, exact turn/transcript reconstruction, tamper-checked no-rewrite resume, upstream invalidation, boundary/property coverage, and short/maximum-size CLI smoke.

## PR 09 delivered surface

- A narrow `google-genai` adapter for the configured Gemini preview model with one bounded SDK request, SDK retries disabled, exact two-speaker configuration, supported distinct voice validation, response-part extraction, and provider prompt version `1.1.0` with explicit synthesis/transcript delimiters.
- Project-owned initial request plus up to three jittered retries near 2, 5, and 12 seconds, with deterministic clock/random/delay injection for tests.
- Raw 24 kHz mono PCM preservation before standard-library WAV packaging, followed by non-empty, media-type, sample-rate, frame, duration, hash, and decode validation.
- Per-segment durable rendering state, fail-closed tamper detection, segment-specific exhaustion guidance, completed-segment resume without rewrites, and final advancement to `audio` only after all segments validate.
- A synthetic offline renderer smoke plus a protected, manually dispatched Gemini live smoke that receives only the Gemini key and retains its sample for one day.
- The initial selected pairing is Maya/Kore and Daniel/Charon, chosen for a firm/informative contrast and retained as profile configuration rather than engine policy.

## PR 10 delivered surface

- One narrow FFmpeg/FFprobe adapter with bounded encode, probe, and full-decode subprocesses plus concise errors that omit command output and runtime paths.
- Manifest-order validation of the existing 24 kHz mono PCM WAV intermediates, followed by direct concatenation and 96 kbps mono 48 kHz MP3 encoding without music, effects, mastering, overlap, or voice modification.
- Codec/container, `audio/mpeg`, duration, sample-rate, channel, byte-size, hash, and full-decode validation before atomic `episode.mp3` promotion and advancement to `publication`.
- Durable final-audio metadata and matching artifact state, invalid-output rollback to resumable `audio`, rendered-segment preservation, tamper detection, and no-rewrite `already_assembled` resume.
- Real FFmpeg integration and smoke coverage for order, conversion, summed duration, missing/empty/corrupt input, timeout/partial cleanup, atomic promotion failure, and final-file tampering on macOS and Ubuntu CI.

## PR 11 delivered surface

- Deterministic escaped show notes with summary, planned timestamps/headings, concise segment context, grouped source links and source dates, a plain-text transcript link, AI disclosure, and generation date; exact transcript export is reused from its validated projection. AntennaPod's web/globe action reaches the full notes and transcript link, and the transcript object/RSS URL pass public retrieval; a separate native transcript view is explicitly tracked after MVP.
- One narrow object-store protocol, thread-safe in-memory test adapter, and bounded boto3 Cloudflare R2 adapter using only object read/write/head/delete operations, explicit media/cache metadata, SHA-256 object metadata, and complete public-body verification.
- Fixed tokenized episode/feed key layout, stable `<feed-id>:<profile-id>:<date>` GUID, RSS 2.0 with enclosure/duration/transcript/show-notes data, same-day upsert, expiry-bound pruning, and valid newest-first ordering.
- Episode-lease-first local feed locking, latest-feed reread, `If-Match`/`If-None-Match: *`, bounded re-read/reapply on 412, safe deferral, harmless orphan assets, and preservation of concurrent revisions.
- Publication state and local artifact hashing without remote token disclosure, plus explicit recovery that preserves valid audio across asset, public-read, lock, and conditional-write failures.
- Offline asset-order/idempotency/concurrency smoke, deterministic two-host initial-feed race coverage, R2 adapter tests, and a main-only disposable R2 probe that receives no Gemini credential or feed token.

## PR 12 delivered surface

- Post-ownership selection of the latest compatible failed/crash-interrupted workspace, atomic provisional-to-resumed lease transfer, preserved run identity, and completed-episode no-op behavior.
- Cross-invocation validation of the current profile and every state-referenced file, with non-resumable validation exhaustion isolated to a fresh run instead of weakening its repair limit.
- One `finalize_run.py` boundary that persists completed or actionable failed state plus the one-screen summary before releasing ownership, and remains idempotent after completion.
- Progressive-disclosure skill routing through collection, editorial, script, TTS, audio, publication, and finalization without an all-in-one CLI, background service, queue, or orchestration framework.
- Deterministic resume coverage at collection, editorial, script, unprepared/prepared/partially rendered TTS, audio, and pre-publication boundaries with unchanged artifact hashes/timestamps and no replacement workspace.
- Complete synthetic offline smoke from profile initialization through golden agent-authored evidence/plan/script, fake speech, real FFmpeg MP3 assembly, fake R2 feed publication, publication-only recovery, final state, and redacted summary.
