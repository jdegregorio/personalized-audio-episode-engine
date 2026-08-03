# MVP implementation sequencing plan

**Status:** Proposed implementation plan
**Source of truth:** [`prd.md`](prd.md)
**Delivery model:** One linear sequence of pull requests, each developed in a new Git worktree
**Target:** A reliable, profile-driven MVP that publishes the world/U.S./Seattle example episode to Cloudflare R2 at a public-but-unguessable feed URL

## 0. Pre-development environment and cloud bootstrap

Offline feature work may start with fixtures, but the team is fully unblocked only when the Gemini account, Cloudflare R2 bucket, least-privilege runtime credentials, public endpoint, GitHub environment, local runtime, Codex scheduler, and AntennaPod device have been prepared. Provision the external account and bucket before PR 01; PR 01 turns the steps below into repository documentation, PR 02 implements `doctor.py`, PR 09 adds the Gemini live smoke, PR 11 adds the R2 probe/publisher, and PR 13 qualifies the schedule.

### 0.1 Selected simple baseline and reasonable alternatives

This is a solo-maintainer project. For accelerated MVP delivery, PR 06 through PR 13 do not wait for or act on GitHub Codex auto-review; feedback from closed PRs is triaged into a separate post-MVP backlog later. GitHub does not require a second human approval.

| Area | Selected simple baseline | Good alternative and tradeoff |
| --- | --- | --- |
| GitHub | One `live-smoke` environment; one minimal `main` ruleset; squash-only linear PRs | No ruleset is simpler but loses an inexpensive guard against accidental direct/force pushes |
| Local secrets | One mode-`0600` env file outside the repository, shared by all worktrees | macOS Keychain/1Password is stronger centralized storage if already available, but adds integration work |
| Secret sync | Local file is the source of truth; helper uploads values one-way with `gh` | Manual GitHub entry avoids a script but is easier to mistype and harder to repeat |
| R2 public endpoint | Use `r2.dev` for the fastest MVP proof, accepting Cloudflare's non-production/rate-limit warning | A custom domain is recommended for ongoing scheduled use and unlocks Cloudflare cache/security controls |
| Runtime storage | Stable mode-`0700` local directories outside feature worktrees | An ignored `runtime/` in the primary checkout is acceptable after PR 01 but less isolated |
| Review | Require final local correctness and simplification passes plus green tests, UAT, and GitHub checks; PR 06–13 do not wait for GitHub Codex auto-review | Add a human review when useful without making it an MVP merge requirement |

No Tailscale, VPN, always-on local web server, database, queue, podcast host, or general cloud orchestration is required. Cloudflare R2 is the only managed publication dependency. The bucket is public at tokenized object URLs, so this design is appropriate only for the public-news MVP; it is not authenticated private storage.

### 0.2 Secrets, credentials, and non-secret variables

Store these secret values locally outside the repository and upload them as GitHub `live-smoke` environment secrets:

| Secret | Purpose | Least privilege / readiness |
| --- | --- | --- |
| `GEMINI_API_KEY` | PR 09 live smoke and production TTS | Selected TTS model is accessible with sufficient billing/quota/region support |
| `PODCAST_FEED_TOKEN` | Unguessable feed and asset path | At least 32 random bytes encoded as URL-safe text; full feed URL is also secret |
| `R2_ACCESS_KEY_ID` | R2 S3-compatible runtime authentication | Belongs to an R2 token restricted to Object Read & Write for one bucket |
| `R2_SECRET_ACCESS_KEY` | R2 S3-compatible runtime authentication | Captured when the token is created; Cloudflare does not show it again |

Set these non-secret values locally and as GitHub `live-smoke` environment variables:

| Variable | Example/requirement |
| --- | --- |
| `R2_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`; never infer it from the public URL |
| `R2_BUCKET_NAME` | Dedicated MVP publication bucket; use a neutral, non-sensitive name |
| `PODCAST_BASE_URL` | Selected public `https://pub-....r2.dev` or custom-domain origin, with no feed token and no trailing object key |
| `R2_RETENTION_DAYS` | Positive integer matching the lifecycle rule for the bucket's `episodes/` prefix; start with `30` unless another retention window is deliberately selected |

`PODCAST_FEED_TOKEN` is access material despite the bucket being public. Never expose it, the full feed URL, R2 secrets, or tokenized object keys in logs, screenshots, chat, issue text, PR evidence, or shell tracing. GitHub cannot return uploaded secret values, so it is a delivery target, not the backup/source of truth.

The MVP does not require an OpenAI API key for Codex-driven editorial work, source-specific API credentials, a Cloudflare global API key, or an R2 administrative token at runtime. Use the interactive Cloudflare account session for one-time setup and give the application only its bucket-scoped token.

### 0.3 One-time Cloudflare R2 bootstrap

The owner completes this dashboard work once; `docs/cloudflare-r2.md` created in PR 01 must preserve the exact current procedure and PR 11 must validate it:

1. Enable/purchase R2 for the Cloudflare account as prompted. Do not make a hard-coded free-tier or price claim in repository documentation.
2. Create one dedicated bucket. Record its exact `R2_BUCKET_NAME` and the account-specific S3 endpoint as `R2_ENDPOINT_URL`.
3. Enable public development access with the bucket's `r2.dev` URL for the fastest MVP setup, or connect a custom domain. Record only the origin as `PODCAST_BASE_URL`. Treat `r2.dev` as proof-of-concept hosting; moving to a custom domain changes configuration, not object layout or application code.
4. Add one lifecycle rule that expires only `episodes/` after `R2_RETENTION_DAYS`. Never apply expiry to `feeds/`; this single prefix continues to work if the feed token rotates, and Cloudflare lifecycle deletion may occur asynchronously after an object reaches its age.
5. Let the helper generate `PODCAST_FEED_TOKEN`, or export an existing 64-or-more-character hexadecimal token before running it. The publisher will use `feeds/<token>/feed.xml` and `episodes/<token>/...` keys.
6. Create an R2 API token with Object Read & Write access restricted to this bucket. Capture its Access Key ID and Secret Access Key immediately; do not grant account-wide admin or bucket-management permission to runtime code.
7. Load the four secrets and four variables with the helper in section 0.4. The helper does not create Cloudflare resources or receive an administrative credential.
8. After PR 11, run its non-sensitive probe: upload a randomly named text object below a dedicated probe prefix, read/HEAD it through the S3 endpoint, fetch it through `PODCAST_BASE_URL`, confirm status/media type, and delete it. Never use the feed token in probe output.
9. Subscribe AntennaPod to `PODCAST_BASE_URL/feeds/<token>/feed.xml` only after the first validated publication; optionally configure its refresh interval and auto-download policy. Disable public access and rotate/revoke the runtime token to roll back the service; rotate the feed token and republish under a new prefix if the feed URL leaks.

Reference documentation: [R2 S3-compatible access](https://developers.cloudflare.com/r2/get-started/s3/), [boto3 example](https://developers.cloudflare.com/r2/examples/aws/boto3/), [public buckets](https://developers.cloudflare.com/r2/buckets/public-buckets/), [API tokens](https://developers.cloudflare.com/r2/api/tokens/), [object lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/), and [consistency](https://developers.cloudflare.com/r2/reference/consistency/).

### 0.4 Prepared worktree-safe setup helper

An ignored `.env` in one checkout does not appear in sibling worktrees. Use the prepared helper rather than copying secrets:

```bash
/Users/jdegregorio/.config/personalized-audio-episode-engine/setup.zsh
```

The helper prompts without echo for Gemini and R2 credentials, generates or preserves the feed token, prompts for the four non-secret variables, creates mode-`0700` local config/runtime directories, and writes `/Users/jdegregorio/.config/personalized-audio-episode-engine/secrets.env` with mode `0600`. When `gh` is authenticated, it uploads the secret values and non-secret variables to the repository's `live-smoke` environment without printing values. `--local-only` skips GitHub synchronization. No secrets file is created until the owner runs the helper.

Load it into any worktree shell with:

```bash
set -a
source /Users/jdegregorio/.config/personalized-audio-episode-engine/secrets.env
set +a
```

Default CI never receives environment secrets. Explicit live jobs name the `live-smoke` environment and request only the values they require. The Gemini job receives no R2 credentials; the R2 smoke receives no Gemini key; a full release UAT may receive both. Never upload GitHub/Codex login credentials or local filesystem paths.

### 0.5 Workstation, production host, and playback prerequisites

Each workstation needs macOS or Ubuntu Linux, Git access to `origin`, a writable sibling directory for `../paee-pr-*` worktrees, `uv` with Python 3.12, FFmpeg/FFprobe, authenticated `gh`, OpenSSL, the signed-in Codex/ChatGPT app, sufficient disk, and stable outbound HTTPS/DNS to GitHub, public research sources, Gemini, and Cloudflare.

The production host additionally needs a stable primary checkout, external mode-`0700` runtime directories, the central secret file, and a power/sleep policy that leaves the app authenticated and the machine connected during scheduled runs. The host need not accept inbound connections or remain awake for later podcast downloads: AntennaPod fetches directly from R2.

The playback device needs AntennaPod and ordinary internet access. No VPN enrollment is required.

### 0.6 Minimal GitHub readiness

The existing setup intentionally stays small:

- Actions are enabled; squash merge and branch auto-delete are enabled.
- The `main-minimal` ruleset requires PRs with zero approvals, blocks deletion/non-fast-forward pushes, and allows the owner/Codex review record to satisfy the solo workflow.
- The `live-smoke` environment exists and is limited to `main`; the helper will load its secrets and variables after the owner enters them locally.
- Vulnerability alerts and automated security fixes are enabled.

PR 01 adds stable CI checks and conversation-resolution enforcement to the existing ruleset rather than creating overlapping rules. Do not add CODEOWNERS, signed-commit enforcement, a merge queue, deployment reviewers, team rules, or another secrets product for the MVP.

### 0.7 Day-zero checks and remaining owner decisions

Run these non-secret checks before PR 01:

```bash
git --version
git fetch origin
git worktree list
test -w ..
gh auth status
uv --version
uv python find 3.12
ffmpeg -version
ffprobe -version
codex --version
openssl version
```

After running the helper, verify presence without printing values:

```bash
for name in GEMINI_API_KEY PODCAST_FEED_TOKEN R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT_URL R2_BUCKET_NAME PODCAST_BASE_URL R2_RETENTION_DAYS; do
  test -n "${(P)name}" || { echo "$name is missing"; exit 1; }
done
```

The only owner choices that block live publication are the Cloudflare account/bucket, `r2.dev` versus custom domain, retention days, Gemini key, and AntennaPod subscription. The selected simplest starting point is `r2.dev` plus 30-day episode retention; choose the custom-domain alternative now if stable ongoing scheduled delivery matters more than fastest setup.

### 0.8 Current readiness snapshot

Read-only/local preparation on August 2, 2026 established:

| Item | State | Remaining action |
| --- | --- | --- |
| Git/origin/worktree parent | Ready; origin configured and sibling directory writable | None before PR 01 |
| Python/`uv` | Python 3.12.4 and `uv` 0.10.3 installed | PR 01 pins the supported range/lock |
| FFmpeg/FFprobe | Ready at 8.0.1 | PR 02 checks capability, not an exact version |
| GitHub CLI/repository | Authenticated; Actions, squash-only, auto-delete, alerts/fixes enabled | PR 01 adds workflows/check names |
| `main` ruleset | `main-minimal` active with PR, deletion, and non-fast-forward controls | Add required checks in PR 01 |
| GitHub environment | `live-smoke` created and limited to `main`; no secrets loaded yet | Run the updated helper after obtaining Gemini/R2 values |
| Local directories/helper | External config/runtime directories and mode-`0700` helper prepared | Run helper; existing local publish directory is no longer a production dependency |
| Cloudflare R2 | Not verifiable/provisioned from repository context | Owner completes section 0.3 and enters values into helper |
| Codex scheduler/Gemini/AntennaPod | Not verifiable from repository context | Complete live probes in owning PRs |

**Environment-ready exit criterion:** Cloudflare bucket/public endpoint/token/lifecycle exist, the helper has loaded all eight values locally and to GitHub, Gemini and R2 probes pass without secret disclosure, and the Codex scheduler plus AntennaPod device are available. CI check wiring completes in PR 01 because those check names do not exist yet.

## 1. Planning principles

This plan translates the approved PRD into a single build order. The PRD remains authoritative if this plan and the product requirements ever differ.

The implementation must preserve these boundaries throughout the sequence:

- The engine remains topic-generic. News-specific taxonomy and policy live only in the example profile and stage inputs.
- Codex performs collection, editorial judgment, and scriptwriting. Python performs deterministic validation, state management, TTS preparation/rendering, audio processing, and publication.
- Files are the system of record. Each completed stage writes and validates a durable artifact before state advances.
- One Codex run handles one episode profile without subagents.
- The MVP uses repository scripts rather than a custom application CLI or ad hoc production code.
- Live services are never required by default CI. Networked Gemini and end-to-end production checks are explicit smoke/UAT gates.
- Runtime data, generated audio, private feed tokens, and credentials are never committed.

## 2. Delivery contract

[`CONTRIBUTORS.md`](CONTRIBUTORS.md) is the canonical worktree, SDLC, testing, documentation, review, and merge policy for every PR in this sequence. Every PR uses a fresh worktree. During accelerated MVP delivery, PR 06 through PR 13 merge after required tests, real UAT, GitHub checks, and final correctness and simplification passes; they do not request, wait for, or act on GitHub Codex auto-review. Closed-PR feedback is triaged into a separate post-MVP backlog later.

## 3. Single MVP PR sequence

| Order | PR | Usable exit signal |
| --- | --- | --- |
| 01 | Repository foundation and delivery guardrails | Clean clones receive fast local and GitHub feedback |
| 02 | Configuration, profile loading, path safety, and doctor | The target machine and arbitrary profiles can be preflighted safely |
| 03 | Artifact contracts, validators, and fixtures | Every pipeline handoff has a versioned, testable contract |
| 04 | Run lifecycle, state, leases, and invalidation | Synthetic runs are durable, resumable, and safe to start concurrently |
| 05 | Capability-aware collection skill | Real native research can produce a valid generic dossier |
| 06 | Editorial planning | A real dossier produces a bounded, valid editorial plan |
| 07 | Grounded two-host scripting | A plan plus full dossier produces an auditable transcript |
| 08 | TTS preparation | The transcript becomes valid, naturally bounded provider requests |
| 09 | Gemini rendering and voice selection | Missing segments render and resume with stable selected voices |
| 10 | Audio assembly | Validated segments become a verified playable MP3 |
| 11 | Cloudflare R2 publication | AntennaPod can consume an ordered, idempotent tokenized feed without lost remote updates |
| 12 | Complete vertical slice | One instruction completes the workflow; CI proves it offline |
| 13 | Scheduled execution and release qualification | Three consecutive unattended scheduled runs pass MVP acceptance |

The sections below are the implementation contracts for those PRs.

Each PR's listed acceptance criteria are cumulative with the definition of done in [`CONTRIBUTORS.md`](CONTRIBUTORS.md). Omission of a documentation or review bullet from an individual PR does not waive those project-wide requirements.

### PR 01 — Repository foundation and delivery guardrails

**Branch/worktree:** `feature/pr-01-foundation` / `../paee-pr-01-foundation`
**Depends on:** Approved PRD only

**Scope**

- Create the Python 3.12 `src/audio_engine` package skeleton and the initial `scripts/` and `tests/` layout.
- Add `pyproject.toml` and a committed `uv.lock` with only the baseline runtime/test dependencies from the PRD.
- Add Ruff, Pyright, pytest, coverage, and pytest marker configuration (`smoke`, `integration`, and `live`).
- Add `.gitignore`, a credential-free `.env.example`, and ignore all `runtime/` content except an optional placeholder needed to preserve directories.
- Extend `AGENTS.md` with the production constraints from PRD section 19.4 while preserving its contributor-policy references.
- Keep `CONTRIBUTORS.md` as the canonical SDLC policy and add `docs/setup.md`, `docs/cloudflare-r2.md`, `docs/operations.md`, `docs/implementation-status.md`, and `docs/cicd.md`, including worktree-safe secret injection and every one-time external R2 dashboard step.
- Add a PR template—including Codex auto-review disposition and the mandatory simplification-review record—and GitHub workflows for integrity, lint/type checks, offline tests, portability, dependency review, and CodeQL.
- Add Markdown/style/link/path validation and safe executable checks for documented repository commands; require the PR template to name documentation impact.
- Add the stable CI check names to the existing `main-minimal` ruleset and document its intentionally small solo-maintainer configuration.

**Out of scope**

- Product schemas, run state, collection logic, Gemini, FFmpeg processing, publication, and scheduler configuration.

**Automated feedback**

- Unit test the package version/import boundary.
- CI builds and imports the package from a locked clean environment on Ubuntu and macOS.
- CI rejects a deliberately unformatted test change and a tracked file under ignored runtime/secret patterns in workflow self-verification fixtures.

**Functional smoke and UAT**

- Smoke: create a clean worktree, run the complete local gate, and import `audio_engine` through `uv run python`.
- UAT: a reviewer follows `CONTRIBUTORS.md` and the linked setup documentation on macOS or Ubuntu and reaches a green local gate without undocumented setup.
- Repository-owner UAT: confirm the one minimal `main` ruleset requires PRs and green checks, blocks force pushes/deletions, and requires zero approvals; record a settings summary in the PR.

**Acceptance criteria**

- `uv sync --locked --all-extras --dev` succeeds from a clean clone with Python 3.12.
- Local and GitHub checks use the same commands and both pass.
- A new developer can identify every required account, tool, secret owner/location, non-secret setting, and deferred verification from `docs/setup.md` without receiving a secret in chat or copying one between worktrees.
- The R2 guide covers prerequisites, `r2.dev` versus custom-domain choice, bucket creation, bucket-scoped Object Read & Write token, lifecycle prefix, secret loading/sync, validation, rollback, token/feed-URL rotation, and AntennaPod setup without relying on screenshots.
- A direct feature push to protected `main` is disallowed after repository settings are applied.
- No workflow receives production secrets on ordinary `pull_request` events.
- The documented worktree, correctness review, simplification review, test, release, rollback, and secret-handling rules are actionable.
- The PR template records the applicable review policy, reviewed commit SHAs, correctness/simplification findings, retained-complexity rationale, and final pass decisions. The original one-or-two-round Codex limit remains historical PR 01 behavior and is superseded for PR 06 through PR 13 by the accelerated policy above.

**PRD traceability:** TR-054; NFR-050–054, NFR-060–061, NFR-070–071, NFR-090–094; sections 19, 25, 26, and 28.

---

### PR 02 — Configuration, profile loading, path safety, and environment doctor

**Branch/worktree:** `feature/pr-02-config-profile` / `../paee-pr-02-config-profile`
**Depends on:** PR 01

**Scope**

- Implement typed YAML/environment configuration with Pydantic v2 and explicit supported schema versions.
- Add the topic-generic episode-profile JSON Schema and matching Python model.
- Add `examples/profiles/world-us-seattle-news.yaml`; keep global/U.S./local semantics entirely in profile data.
- Implement timezone-aware episode-date resolution, redaction helpers, configured root resolution, safe R2 object-key construction, and rejection of paths/keys outside allowed runtime, staging, input, feed, and episode roots.
- Implement `scripts/doctor.py --profile <path>` with `--help`, concise output, non-zero failures, and checks for Python, `uv`, locked dependencies, FFmpeg, FFprobe, required Gemini/R2/feed environment variables, sane endpoint/base URL/bucket/retention settings, writable runtime roots, profile validity, and required source-capability availability where detectable. Preflight validates configuration shape without uploading data.
- Extend `.env.example` and setup/profile-authoring documentation without adding real credentials or machine-specific paths.

**Out of scope**

- Creating runs, leases, artifact schemas other than the profile, research, TTS API calls, or publication.

**Automated feedback**

- Unit tests cover valid/arbitrary topic profiles, malformed YAML, executable-looking YAML tags, unsupported versions, timezone/date edges, missing settings, redaction, symlink/path traversal, and non-writable roots.
- Contract tests prove the example profile validates and an unrelated synthetic topic/profile validates through the same code.
- CI smoke supplies dummy settings, fake credentials/tokens, and temporary roots; external binaries are checked without making network calls.

**Functional smoke and UAT**

- Smoke: run `doctor.py` once with a complete temporary configuration and once with required settings omitted; confirm success and actionable failure respectively.
- UAT: on the target Mac, load the external central env file, run the documented doctor command, and confirm Python/uv/FFmpeg/FFprobe/profile/runtime/R2 configuration checks are understandable without opening JSON or exposing a value.

**Acceptance criteria**

- The example and arbitrary-topic profiles validate without engine knowledge of their section identifiers.
- Unknown required schema versions and unsafe paths fail before any output mutation.
- Doctor redacts the feed token, full feed URL/object keys, Gemini key, and both R2 credential fields and identifies exactly what the operator must fix.
- Profile publication config references environment-variable names rather than embedding bucket, endpoint, URL, token, or retention values.
- Configuration contains no hard-coded platform paths and uses the profile timezone for episode dates.

**PRD traceability:** TR-046, TR-048–049; FR-002, FR-005, FR-010–015; NFR-041–043, NFR-051–053, NFR-060–062, NFR-067, NFR-070–071, NFR-090–094; AC-001, AC-003, AC-018.

---

### PR 03 — Versioned artifact contracts, validators, and golden fixtures

**Branch/worktree:** `feature/pr-03-artifact-contracts` / `../paee-pr-03-artifact-contracts`
**Depends on:** PR 02

**Scope**

- Add versioned JSON Schemas and Pydantic models for collection request, evidence dossier, editorial plan, episode script, published episode, and run state.
- Define topic-generic IDs, flexible classifications, timestamps, claims, claim supports, source provenance, prompt versions, and artifact references.
- Implement `scripts/validate_artifact.py --type ... --input ...` and reusable validation/reporting helpers.
- Implement evidence referential validation: unique IDs, claim/support/source linkage, excerpts or precise locators, access/retrieval metadata, independence groups, allowed support types, dossier limits, and safe locators.
- Implement baseline cross-artifact validation hooks for plans and scripts; later PRs add phase-specific policy warnings.
- Add synthetic golden fixtures for every artifact, plus invalid contract fixtures required by PRD section 28.2.

**Out of scope**

- Agent prompts, live collection, run-state mutation, script prose-quality warnings, TTS, and publication behavior.

**Automated feedback**

- Contract tests cover every valid fixture and all required invalid cases: missing/duplicate/unknown IDs, missing support, bad timestamps/status, false independent corroboration, unsupported versions, oversized dossiers, malicious paths, and prompt-injection text treated as inert data.
- Tests verify concise machine-readable failures on stdout/stderr and full validation reports when a report output is requested.
- Schema/fixture validation becomes a permanent CI integrity job.

**Functional smoke and UAT**

- Smoke: validate all golden artifacts through the public script, then mutate one claim reference and confirm a non-zero result identifies its exact JSON path and error code.
- UAT: a reviewer audits one factual script turn through claim, claim-support, and source fixtures and confirms the chain is directly traceable.

**Acceptance criteria**

- Every artifact declares a supported version and rejects unsupported required versions clearly.
- The same evidence schema accepts public-web and synthetic connector-style locators without source-specific engine code.
- Every fixture is synthetic and copyright-safe.
- Validation never executes, imports, or follows instructions contained in source material.
- Inputs are never modified by validation.

**PRD traceability:** FR-011–013, FR-040–044, FR-060, FR-090, FR-097, FR-100; NFR-041–045, NFR-054, NFR-063–064; AC-005, AC-007, AC-011; sections 20, 21, and 28.2–28.5.

---

### PR 04 — Run initialization, durable state, leases, and invalidation

**Branch/worktree:** `feature/pr-04-run-lifecycle` / `../paee-pr-04-run-lifecycle`
**Depends on:** PR 03

**Scope**

- Implement atomic file writes, SHA-256 artifact hashing, canonical episode keys, unique run IDs, and the prescribed date/profile/run directory layout.
- Implement `scripts/init_run.py --profile <path>` to acquire ownership before selecting/creating/resuming a run, then create the collection request, `state.json`, and initial `summary.md`.
- Record required provenance: profile/engine/skill/prompt versions, Git commit, dates, models when observable, artifact locations/hashes, and redacted locations.
- Implement the state machine, valid transitions, last-completed-valid stage, failure details, heartbeat refresh, and ownership checks for every mutating helper.
- Implement atomic exclusive episode leases, live-owner no-op behavior, owner-only refresh/release, terminal release, stale quarantine/recovery, and configurable maximum run age.
- Implement dependency invalidation rules for profile, dossier, plan, and script hash changes.

**Out of scope**

- Feed-level lock, collection decisions, editorial/script generation, rendering, and successful publication finalization.

**Automated feedback**

- Unit tests cover state transitions, atomic-write failure, hashing, invalidation, lease ownership/heartbeat/release, terminal owners, stale recovery, and secret redaction.
- Concurrency integration tests start simultaneous same-key initializations and assert one owner, one successful no-op, and no no-op run artifacts.
- Race tests verify only one stale-lease recoverer wins and a non-owner cannot mutate state or release the lease.

**Functional smoke and UAT**

- Smoke: initialize a synthetic profile, inspect the created request/state/summary, rerun concurrently, and confirm the second invocation reports a successful no-op.
- UAT: simulate an abandoned lease with controlled time, verify takeover is refused before expiry, then recovered through atomic quarantine after expiry without manual deletion.

**Acceptance criteria**

- Ownership is acquired before any run artifact is selected, created, resumed, or mutated.
- State advances only after an artifact is atomically written, validated, and hashed.
- A profile/artifact change invalidates exactly its downstream stages and retains valid upstream work.
- Every acquired invocation has a human-readable one-screen summary, including failure/recovery guidance.
- All concurrency tests are repeatable on macOS and Ubuntu.

**PRD traceability:** FR-001–005, FR-026, FR-120, FR-130–139; NFR-014, NFR-033, NFR-062; AC-016–017, AC-020; sections 17, 18, 27, and 28.7.

---

### PR 05 — Core skill and capability-aware evidence collection

**Branch/worktree:** `feature/pr-05-collection-skill` / `../paee-pr-05-collection-skill`
**Depends on:** PR 04

**Scope**

- Add `.agents/skills/produce-audio-episode/SKILL.md` with concise entry conditions, high-level phase routing, documented commands, failure rules, and progressive-disclosure references.
- Add `workflow.md`, `evidence-collection.md`, and `run-state.md` references; defer editorial, script, TTS, and publication detail to later PRs.
- Instruct Codex to inspect available capabilities, use a suitable specialized capability when useful, and use native web research for allowed public-web profiles when none is suitable.
- Define the exact handoff from collection request to one evidence dossier and the one-repair validation loop.
- Require high-recall bounded collection, claim-level support, time/provenance distinctions, source originality/independence, short excerpts, and untrusted-source handling.
- Add reusable state-update support for collection method/name/version and validation outcomes.
- Add `docs/optional-collectors.md` and collection troubleshooting guidance; clearly mark all specialized collectors as optional and do not install one.

**Out of scope**

- Any source-specific API client, automatic skill installation, editorial selection, scriptwriting, or audio.

**Automated feedback**

- Contract/integration tests adapt two synthetic collection-method outputs (native and specialized) into the identical dossier validator.
- Tests cover specialized-capability failure with allowed fallback, missing required authenticated capability, one repair, repair exhaustion, hard/warning dossier limits, and prompt-injection content.
- A skill-package integrity test verifies progressive-disclosure links and documented commands exist.

**Functional smoke and UAT**

- Smoke: use fixture research results to produce, validate, record, and resume from a dossier through the skill's documented path.
- UAT: run one real current-news collection with native research and, if a suitable capability is installed, one with that capability; validate both through the same script and inspect candidate breadth and claim support. Only redacted validation summaries are retained.

**Acceptance criteria**

- Native public-web fallback completes without any separately installed collector.
- A profile requiring an unavailable authenticated source stops before editorial work with configuration guidance.
- The dossier contains more credible candidates than a normal final episode needs, within configured limits.
- Source content cannot authorize shell commands, installs, credential access, or workflow changes.
- The repository contains no source-specific integration code.

**PRD traceability:** FR-020–044; NFR-030–035, NFR-043, NFR-063–066; AC-002–007; sections 5.2, 19.2–19.5, 21, and 30.

---

### PR 06 — Editorial planning phase and deterministic plan validation

**Branch/worktree:** `feature/pr-06-editorial-plan` / `../paee-pr-06-editorial-plan`
**Depends on:** PR 05

**Scope**

- Add versioned editorial-planning instructions and prompt metadata behind the skill's progressive-disclosure route.
- Define the single Codex phase that consumes the complete validated dossier and profile and writes one structured editorial plan.
- Complete plan validation for selected/excluded candidates, required/optional claims, segment order, treatment time, profile-defined classifications, host leads/dynamics, transitions, opening, closing, limits, and duration.
- Keep exclusion reasons extensible and profile-defined; do not add numerical ranking, deterministic relevance scoring, ensembles, or a second model.
- Add state transitions, validation report writing, one recorded repair, downstream hash invalidation, and failure recovery guidance for this phase.
- Add golden plans covering an ordinary episode, a shorter useful episode, an optional empty section, source disagreement, and arbitrary non-news taxonomy.

**Out of scope**

- Writing spoken dialogue, semantic fact-checking, TTS, and publication.

**Automated feedback**

- Tests cover missing/duplicated candidates, unknown claims, unsupported profile classifications, invalid lead host, duration/item bounds, missing exclusion reasons, and one-repair exhaustion.
- Contract tests prove the plan consumes the full dossier and references only valid candidate/claim IDs.
- CI smoke drives a fixture run from validated dossier to validated plan and verifies state/hash updates.

**Functional smoke and UAT**

- Smoke: validate the golden dossier-to-plan path and a shorter optional-section plan.
- UAT: in a distinct Codex editorial phase, create a plan from the real dossier produced in PR 05; inspect selections, exclusions, source-conflict notes, timing, and usefulness before validation.

**Acceptance criteria**

- The validated plan separately records what is included, what is excluded, and why.
- Planned duration and count honor profile bounds without hard-coded news taxonomy.
- An invalid plan receives at most one recorded repair and cannot advance if still invalid.
- The plan artifact records the explicit prompt version and input hashes.

**PRD traceability:** FR-050–062; NFR-032, NFR-044–045; AC-006–009; sections 10.6–10.7 and 24.2.

---

### PR 07 — Grounded two-host script phase and transcript projection

**Branch/worktree:** `feature/pr-07-script-grounding` / `../paee-pr-07-script-grounding`
**Depends on:** PR 06

**Scope**

- Add versioned scriptwriting/host-performance instructions as a separate skill phase.
- Complete episode-script validation for exactly two configured speakers, valid turn types, factual/analysis claim linkage, candidate/segment references, speaker names, duration, URL/citation exclusion, and no third speaker.
- Add warnings for performance-tag excess, reaction-only turns, host word share over 70%, consecutive turns, stock phrases, missing takeaways, and preferred-duration misses; allow profile-configured fatal warnings.
- Preserve qualifications, attribution, disagreement, uncertainty, and the distinction between fact and host analysis.
- Generate or verify the plain-text transcript as a deterministic projection of the validated structured script so TTS cannot diverge from the auditable script.
- Record prompt/input versions, validation, one repair, transcript hash, and downstream invalidation in state.
- Add balanced, imbalanced, disputed-source, arbitrary-topic, and malicious-text golden fixtures.

**Out of scope**

- A third LLM fact-checker, audio segmentation, voice synthesis, and publication.

**Automated feedback**

- Tests cover every script error/warning in PRD section 13, transcript equivalence, forbidden URLs/citation syntax, missing claim lineage, invalid speakers, qualification loss, and repair exhaustion.
- Cross-artifact tests trace every factual turn through plan/candidate/claim/support/source.
- CI smoke drives a fixture run from plan+dossier to validated script+transcript and inspects both host contributions.

**Functional smoke and UAT**

- Smoke: render the golden structured script to plain text, revalidate it, and prove a changed spoken fact or unsupported third speaker fails.
- UAT: in a fresh, separate Codex script phase, create a script using both the real plan and complete dossier; read the transcript aloud and inspect host balance, naturalness, uncertainty, and factual lineage.

**Acceptance criteria**

- Editorial plan and episode script remain separate validated artifacts.
- Every factual spoken turn has an auditable claim chain to underlying source support.
- Both configured hosts contribute materially; warnings surface weak balance without silently rewriting prose.
- Spoken output contains no URLs, citation syntax, fabricated personal experience, or unconfigured speaker.
- The transcript contains exactly the validated spoken material plus supported performance annotations.

**PRD traceability:** FR-070–103; AC-008–011; sections 11–13 and 24.2.

---

### PR 08 — Provider-neutral TTS preparation and segmentation

**Branch/worktree:** `feature/pr-08-tts-preparation` / `../paee-pr-08-tts-preparation`
**Depends on:** PR 07

**Scope**

- Add the provider-neutral speech-renderer interface and Gemini model capability configuration without making network calls.
- Implement bounded token estimation and enforce the configured 7,000-token safe limit and 8,192-token absolute model limit before every prospective request.
- Implement `scripts/prepare_tts.py --run <path>` to split at planned-segment/section/recap boundaries, target two-to-four-minute chunks, and avoid mid-discussion splits unless required.
- Produce an ordered, versioned TTS manifest and atomic segment prompt files containing stable scene/host descriptions, exact speaker names/transcript, director notes, position, and minimal continuity context.
- Persist manifest/prompt hashes and preparation state so upstream changes invalidate exactly the required audio artifacts.

**Out of scope**

- Gemini credentials/API calls, retries, generated audio, FFmpeg concatenation, and voice-pair selection.

**Automated feedback**

- Unit tests cover token boundaries, absolute-limit configuration rejection, natural-boundary preference, forced oversized discussion splits, deterministic ordering, exact speaker-name matching, continuity context, and prompt-instruction leakage.
- Property/boundary tests prove no emitted segment exceeds the configured safe limit.
- CI smoke prepares segments from the golden script and validates the manifest and prompt files.

**Functional smoke and UAT**

- Smoke: run `prepare_tts.py` on short and maximum-size fixture scripts; inspect segment count, token estimates, boundaries, state, and idempotent rerun behavior.
- UAT: prepare the real PR 07 script and confirm each segment is a coherent two-to-four-minute section with no missing or duplicated turns.

**Acceptance criteria**

- Every provider request is preflighted below its configured token limit.
- Segment concatenation order exactly reconstructs the validated transcript.
- Voice assignments, speaker names, and scene direction are identical across segments.
- A changed script invalidates prepared segments; an unchanged rerun does not rewrite valid outputs.

**PRD traceability:** TR-002–012; FR-100; NFR-040; AC-012–013; sections 14.1–14.2 and 22.4.

---

### PR 09 — Gemini rendering, retry/resume, and voice selection

**Branch/worktree:** `feature/pr-09-gemini-renderer` / `../paee-pr-09-gemini-renderer`
**Depends on:** PR 08

**Scope**

- Implement the `google-genai` Gemini multi-speaker renderer behind the speech interface using configurable `gemini-3.1-flash-tts-preview` defaults.
- Add bounded request timeouts, no-more-than-two-speaker configuration, exact speaker names, raw response preservation, and per-segment decodability/duration/empty/text-response validation.
- Implement `scripts/render_audio.py --run <path>` for missing segments only, with up to three exponential-backoff+jitter retries and durable successful-segment state after every response.
- Make retry exhaustion preserve completed segments, prevent publication readiness, and provide segment-specific resume guidance.
- Add deterministic mocked Gemini responses and failure injection for CI.
- Add a protected, manually dispatched GitHub `live-smoke` workflow for a 60–90-second synthetic conversation.
- Run and document a small live voice bakeoff, select one stable female/male pairing with the owner, and replace profile placeholders with the chosen configurable voice IDs.

**Out of scope**

- Final MP3 concatenation, creative post-processing, RSS publication, and automated audio-quality judging.

**Automated feedback**

- Mocked tests cover success, empty audio, text instead of audio, HTTP 500, rate limiting, timeout, retry success/exhaustion, invalid voices, implausibly short/undecodable output, and resume after one completed segment.
- Tests replace delays with a deterministic clock/random source and assert the approximate 2/5/12-second policy without slowing CI.
- CI offline smoke renders all fixture segments with a fake provider and verifies raw/audio files and state.

**Functional smoke and UAT**

- Smoke: run the documented live command locally before merge with a short synthetic transcript; download/play the artifact and inspect the validation metadata. Immediately after merge, dispatch the new protected workflow on `main` and require it to pass before PR 10 starts.
- UAT: listen to several 60–90-second voice-pair samples for distinction, stability, pacing, instruction leakage, and conversational fit; record the selected voice IDs and qualitative decision without implementing a scoring system.
- Resume UAT: force one middle segment to fail, rerun after removing the fault, and confirm completed segments retain hashes/timestamps and are not rerendered.

**Acceptance criteria**

- A live request audibly contains exactly two stable, distinguishable configured speakers.
- Raw returned audio is preserved before conversion and every completed segment is decodable and plausibly timed.
- Transient failure rerenders only the failed segment; exhausted retries never discard completed segments or mark the episode publishable.
- Secrets are absent from logs, artifacts, and pull-request workflows.

**PRD traceability:** TR-001–021; NFR-012, NFR-022, NFR-040, NFR-062; AC-012–014; sections 14.3–14.4 and 28.3.

---

### PR 10 — FFmpeg assembly and final-audio validation

**Branch/worktree:** `feature/pr-10-audio-assembly` / `../paee-pr-10-audio-assembly`
**Depends on:** PR 09

**Scope**

- Implement the FFmpeg/FFprobe wrapper with bounded subprocess timeouts and concise, redacted errors.
- Normalize provider output to a standard intermediate WAV representation where needed.
- Concatenate validated segments in manifest order and encode a speech-appropriate mono MP3 at 44.1 or 48 kHz.
- Validate final codec, MIME expectation, duration, sample rate, channels, file size, and decode health before atomically recording `episode.mp3` and final-audio state.
- Keep technical conversion separate from provider code and add no music, effects, overlap, mastering, compression for performance, or voice modification.

**Out of scope**

- Show notes, RSS/R2 publication, loudness mastering, or subjective automated audio evaluation.

**Automated feedback**

- Tests use short synthetic audio generated during test setup to cover order, conversion, format, duration tolerance, corrupted/missing/empty segments, timeout, partial output, and atomic failure cleanup.
- An integration test proves the assembled duration approximates the sum of inputs and no invalid MP3 becomes publication-ready.
- CI runs audio tests with pinned/documented FFmpeg availability on Ubuntu and macOS.

**Functional smoke and UAT**

- Smoke: assemble deterministic fixture segments, inspect with `ffprobe`, decode the full file, and compare metadata to expected values.
- UAT: assemble and play the live PR 09 sample end to end, checking order, boundary continuity, both voices, and absence of unexpected post-processing.

**Acceptance criteria**

- Only a validated `audio/mpeg` final file advances state.
- Segment order is exact and failed assembly leaves prior segment files reusable.
- The final validation result is stored in state and summarized for the user.
- FFmpeg failures are bounded and provide a documented recovery action.

**PRD traceability:** TR-030–036; NFR-013–014, NFR-022; sections 15, 22.5, and 28.3.

---

### PR 11 — Cloudflare R2 publication, RSS concurrency, retention, and AntennaPod

**Branch/worktree:** `feature/pr-11-publication` / `../paee-pr-11-publication`
**Depends on:** PR 10

**Scope**

- Implement show-note generation, transcript export, published episode metadata, stable GUIDs, and standards-compatible RSS 2.0.
- Implement the narrow publication interface plus a `boto3` Cloudflare R2 adapter; retain a local/in-memory adapter only for deterministic development and tests.
- Implement the required remote keys: `feeds/<token>/feed.xml` and `episodes/<token>/<profile-id>-<date>/{episode.mp3,transcript.txt,show-notes.html,episode.json}`.
- Implement `scripts/publish_episode.py --run <path>` to validate final audio, upload all episode assets with correct media types, verify them before discoverability, acquire the feed advisory lock, download the latest remote feed and ETag, prune entries at/before the configured lifecycle boundary, merge and validate the episode, then upload the feed last.
- Write `feed.xml` with `application/rss+xml` and `Cache-Control: no-cache, no-store, must-revalidate`; write MP3 as `audio/mpeg` and every companion object with its correct media type.
- Make an existing-feed upload conditional on `If-Match` and initial creation conditional on `If-None-Match: *`. On precondition failure, perform a bounded re-read/reapply retry or defer publication without losing the concurrent feed revision.
- Implement rerun upsert semantics for the same profile/date without duplicate items.
- Implement bounded feed-lock acquisition, deferred publication state, publication-only resume, and the required episode-lease-then-feed-lock ordering.
- Reject unsafe object keys and redact credentials, tokenized keys, and complete feed URLs in logs/state/PR evidence.
- Add a manually dispatched R2 smoke that uploads, S3-HEADs, publicly fetches, and deletes a non-sensitive randomly named probe object. It must not publish or reveal the production feed.
- Complete `docs/cloudflare-r2.md`, setup, operations, troubleshooting, security/privacy, rotation, retention, recovery, and AntennaPod instructions against the implemented commands and observed dashboard behavior.

**Out of scope**

- R2 bucket/domain/token/lifecycle administration from runtime code; additional storage providers; authenticated/encrypted personal-data feeds; CDN optimization; and scheduler configuration.

**Automated feedback**

- Fake-client or `botocore.stub.Stubber` tests cover valid XML, enclosure MIME/length, duration, stable GUID, no duplicate daily item, URL construction, object metadata/cache headers, asset-before-feed ordering, HEAD/public-fetch failure, rerun readability, and no feed write after an asset failure.
- Tests cover `If-Match`, `If-None-Match: *`, simulated precondition conflicts, bounded re-read/reapply, non-convergence deferral, initial-feed races, and harmless orphan assets. A concurrent external update is never overwritten.
- Retention tests prove RSS items are pruned no later than the configured episode expiry boundary and `feeds/` is never selected for lifecycle deletion.
- Concurrent integration tests publish two different episode keys to one feed and prove both survive; feed-lock timeout must defer without losing audio.
- Object-key and redaction tests include malicious tokens, traversal, ambiguous base URLs, and log-capture cases. Default tests have network disabled and use no Cloudflare credential.

**Functional smoke and UAT**

- Offline smoke: publish a fixture episode through the fake adapter, inspect the exact logical objects and headers, rerun, and confirm one updated feed item.
- Live R2 smoke: run the disposable probe locally from the PR worktree using the central env file, confirm S3 and public reads plus cleanup, and attach only redacted status/content-type evidence. Immediately after merge, dispatch the same protected job on `main` and require it to pass before PR 12 starts.
- UAT: publish the live sample to R2, fetch the feed and every linked asset publicly, subscribe with AntennaPod, play it, open the full HTML show notes and transcript link through the episode's web/globe action, and confirm a rerun does not duplicate it. Require the plain-text transcript URL to resolve publicly; a separate native transcript view inside AntennaPod is a post-MVP follow-up rather than a PR 11 gate.
- Concurrency UAT: run two fixture publications plus one injected external ETag change and inspect a final feed containing every entry.
- Bootstrap UAT: an owner follows `docs/cloudflare-r2.md` from bucket setup through probe/rotation/rollback without relying on undocumented knowledge; record any dashboard drift in the same PR.

**Acceptance criteria**

- The remote feed is always either the previous valid version or the complete new valid version; it never references an unverified asset and never overwrites a concurrent ETag revision.
- Publication failure, lock deferral, or exhausted precondition retry preserves final audio and can resume without rendering again.
- Feed retention and R2 lifecycle configuration agree, and the feed object is retained outside the expiring prefix.
- AntennaPod discovers and plays the R2-hosted episode, and its web/globe action reaches the full HTML notes and published plain-text transcript over ordinary internet access. A separate native transcript view is not an MVP gate.
- The committed repository contains neither the feed token nor generated publication output.
- Runtime R2 credentials have Object Read & Write access only to the configured bucket, and application code contains no administrative Cloudflare operation.

**PRD traceability:** FR-110–112, FR-131, FR-140–141; TR-040–054; NFR-001–005, NFR-013, NFR-040, NFR-060–067, NFR-090–094; AC-015–016, AC-018, AC-020; sections 16 and 28.4.

---

### PR 12 — Complete workflow, resume/finalization, and offline vertical slice

**Branch/worktree:** `feature/pr-12-vertical-slice` / `../paee-pr-12-vertical-slice`
**Depends on:** PR 11

**Scope**

- Complete all progressive-disclosure skill references for editorial planning, scriptwriting, TTS rendering, publishing, and failure recovery.
- Wire documented stage commands and state transitions into one coherent Codex-driven workflow without adding an all-in-one custom CLI.
- Implement `scripts/finalize_run.py --run <path>` for terminal success/failure, summary generation, state persistence before episode-lease release, and concise final locations.
- Complete resume logic at collection, plan, script, each TTS segment, final audio, and pre-publication boundaries. After acquiring episode ownership, initialization must locate and select the latest compatible failed or crash-interrupted workspace for the canonical episode key instead of creating a fresh run, then restore its last completed valid stage.
- Ensure upstream hash changes invalidate dependent outputs while publication-only retry preserves valid audio.
- Add an offline synthetic vertical-slice test using golden agent-authored artifacts, the fake renderer, and fake R2 adapter: profile → initialization → dossier → plan → script/transcript → TTS segments → MP3 → publication → final summary.
- Complete README, setup, profile-authoring, command, troubleshooting, security/privacy, Cloudflare R2 operations, resume, implementation-status, and optional-capability documentation.

**Out of scope**

- Scheduled-task activation, new episode profiles, source-specific collectors, analytics, dashboard, database, or additional cloud services/providers.

**Automated feedback**

- The offline vertical slice becomes the required `pytest -m smoke` CI job and verifies actual output contents, hashes, stage ordering, feed entry, and one-screen summary.
- Failure-matrix integration tests cover every row in PRD section 30 and assert last valid stage, preserved artifacts, non-publication when unsafe, and actionable recovery text.
- Resume tests fail each boundary once, reacquire through `scripts/init_run.py`, select the prior workspace only after ownership, and prove its run identity plus valid upstream artifact hashes/timestamps are unchanged and no replacement run directory was created.
- A repository audit test rejects topic-specific source clients, undocumented production shell commands, runtime artifacts, and broken skill-reference links.

**Functional smoke and UAT**

- Smoke: execute the complete offline path from a clean temporary root using only documented commands and confirm a playable synthetic MP3 plus valid tokenized feed in the fake object store.
- UAT: issue one user-level instruction invoking the skill and example profile, allow native real-world research, live Gemini, and R2 publication, then inspect the dossier, separate plan/script, final audio, summary, and public R2 feed.
- Recovery UAT: induce a publication failure after valid audio, then perform publication-only resume and confirm the audio hash is unchanged.

**Acceptance criteria**

- One user-level Codex instruction can complete the manual workflow without source edits or undocumented commands.
- `summary.md` alone states success/failure, last valid stage, audio/publication status, warnings, redacted locations, and recovery action.
- Default CI proves the whole deterministic pipeline without current news, external research, Gemini, or real secrets.
- A live manual run produces the complete required artifact layout and valid playable output.
- The core remains profile-driven and contains no source-specific integrations or batch/subagent orchestration.

**PRD traceability:** FR-120, FR-133–137; NFR-010–014, NFR-030–035, NFR-080–082, NFR-090–094; AC-001–018; sections 9, 17, 18, 19, 22, 27, 28.6, and 30.

---

### PR 13 — Scheduled execution and MVP release qualification

**Branch/worktree:** `feature/pr-13-release-qualification` / `../paee-pr-13-release-qualification`
**Depends on:** PR 12

**Scope**

- Add the exact scheduled Codex task prompt, model/configuration guidance, workspace/network/permission requirements, production-run restrictions, and operator setup/runbook.
- Add a release checklist and a redacted UAT evidence template covering the PRD acceptance criteria.
- Add a release-candidate GitHub workflow that reruns all offline checks and packages safe validation reports; production feed publication remains in the local scheduled task rather than GitHub Actions.
- Configure and exercise one daily local scheduled task against the release-candidate checkout, using the example profile and a new independent Codex context per invocation.
- Retain the PR 13 worktree at a stable, unchanged path for the entire qualification streak; do not reuse it for other work.
- Qualify three consecutive scheduled runs without manual source changes or intermediate intervention.
- Exercise final AntennaPod, idempotency, recovery, and concurrency acceptance cases and record redacted results in the PR.
- After merge and final green `main`, move/confirm the durable schedule against the stable primary checkout and tag the approved MVP release.

**Out of scope**

- Feature expansion, quality metrics/analytics, additional schedules, additional profiles, additional cloud services/providers, or opportunistic refactors. Defects found during qualification must receive the smallest directly related fix and a regression test; the three-run streak restarts after any code/config change.

**Automated feedback**

- All earlier offline quality, unit, contract, integration, smoke, portability, and security checks are required.
- A task-prompt contract test verifies the profile, timezone, skill invocation, native fallback, no-source-modification rule, validation gates, resume behavior, and final-summary return instruction.
- A clean-checkout test proves the scheduled runbook references only existing commands/files and production code remains unchanged during a fixture run.

**Functional smoke and UAT**

- Smoke: invoke the scheduled prompt manually in a fresh Codex context and verify one complete live episode before enabling the schedule.
- Scheduled UAT: three consecutive scheduled dates each produce a validated playable MP3 without manual code/config/intermediate changes; record run IDs, dates, audio validation, publication result, and redacted locations.
- Feed UAT: AntennaPod refreshes the R2 URL, plays the episode, and reaches the full source notes plus transcript link through its web/globe action; the transcript object resolves independently, public responses have expected media types, and same-day rerun updates rather than duplicates. A separate native AntennaPod transcript view remains outside the MVP gate.
- Concurrency UAT: same-key simultaneous initialization produces one owner/one no-op; different-key and external-ETag concurrent publication preserves every feed item.
- Recovery UAT: demonstrate failed-segment resume and publication-only resume without repeating successful work.

**Acceptance criteria**

- The schedule runs once per configured morning in the project, with network/workspace access and the narrowest required permissions.
- All three consecutive scheduled runs produce valid playable audio with no manual intermediate intervention or code change.
- The final acceptance record demonstrates AC-001 through AC-020 and contains no secrets or sensitive runtime data.
- Production runs leave tracked source, dependency, schema, and profile files unchanged.
- The stable main checkout passes the complete release-candidate workflow before the MVP tag is created.

**PRD traceability:** NFR-010–011, NFR-065, NFR-080; AC-004, AC-015–020; sections 23, 24, 28.6–28.7, 29, 31, and 32 phase 6.

## 4. Cross-PR acceptance map

| MVP acceptance criterion | Implemented primarily in | Proven finally in |
| --- | --- | --- |
| AC-001 Generic profile execution | PR 02, PR 03 | PR 12 |
| AC-002 Flexible collection/native fallback | PR 05 | PR 12–13 |
| AC-003 No embedded source integration | PR 02, PR 05 | PR 12 repository audit |
| AC-004 Scheduled end-to-end run | PR 13 | PR 13 three-run UAT |
| AC-005 Structured evidence | PR 03, PR 05 | PR 12 |
| AC-006 High-recall collection | PR 05 | PR 12–13 |
| AC-007 Auditable claim support | PR 03, PR 05 | PR 07, PR 12 |
| AC-008 Separate plan and script | PR 06–07 | PR 12 |
| AC-009 Full evidence available to script | PR 07 | PR 12 |
| AC-010 Two valuable hosts | PR 07 | PR 09, PR 12–13 |
| AC-011 Claim lineage | PR 03, PR 07 | PR 12 |
| AC-012 Multi-speaker audio | PR 08–09 | PR 12–13 |
| AC-013 Natural provider-aware segmentation | PR 08 | PR 12–13 |
| AC-014 TTS retry handling | PR 09 | PR 12–13 |
| AC-015 Cloudflare R2 RSS/AntennaPod | PR 11 | PR 13 |
| AC-016 Idempotency | PR 04, PR 11 | PR 12–13 |
| AC-017 Human-readable result | PR 04, PR 12 | PR 13 |
| AC-018 Reproducible setup | PR 01–02, PR 12 | PR 13 clean checkout |
| AC-019 Three-run reliability | PR 12 foundation | PR 13 three-run UAT |
| AC-020 Safe concurrency | PR 04, PR 11 | PR 13 |

## 5. Final MVP release gate

The MVP is complete only when PR 13 is merged and all of the following are true:

1. The protected `main` branch passes the complete secret-free GitHub Actions suite on Ubuntu and macOS.
2. A clean local checkout passes doctor, the full local gate, and the offline vertical slice using only documented commands.
3. The native research fallback creates a current, valid, high-recall dossier.
4. Separate valid editorial-plan and script artifacts exist, and every factual turn has auditable lineage.
5. Gemini renders all naturally bounded segments with the selected two voices; transient retry and resume are demonstrated.
6. FFprobe validates the final MP3 and a human confirms it plays with correct order and both speakers.
7. R2 publication exposes valid audio, transcript, show notes, metadata, and RSS through the tokenized public endpoint, with expected media/cache metadata and assets published before the conditional feed update.
8. AntennaPod discovers, refreshes, and plays the feed; a same-day rerun creates no duplicate.
9. Same-episode, shared-feed, and external-ETag concurrency acceptance tests pass without a lost feed revision.
10. Three consecutive scheduled runs create valid playable audio without manual code/config changes or intermediate intervention.
11. `summary.md` correctly reports each final outcome and recovery path without exposing secrets.
12. The source tree remains unchanged by production runs, runtime artifacts remain ignored, no source-specific collector or deferred feature entered the MVP, and every PR's implementation-status and affected operator/developer documentation are current.

If any release-gate item fails, the MVP is not accepted. Add the smallest regression test and fix within the owning release-qualification scope, rerun the full local and GitHub gates, and restart any affected consecutive-run qualification window.

## 6. Post-MVP follow-up backlog

### AntennaPod plain-text transcript discoverability

- **Observed:** August 3, 2026 physical-device UAT confirmed feed subscription, refresh, streaming, download/playback, episode metadata, and the in-app description. AntennaPod's web/globe action opened the full HTML show notes with their transcript link, and the RSS-advertised `transcript.txt` returned HTTP `200` with `text/plain`. AntennaPod did not expose a separate native transcript view.
- **MVP disposition:** Transcript and show-notes reachability pass through the web/globe action, so the missing native transcript view does not block the audio-first MVP. Keep publishing and verifying the required plain-text transcript and its stable RSS URL, but do not add speculative VTT, SRT, JSON, timing generation, or client-specific feed variants during PR 11–13.
- **Post-MVP acceptance:** Reproduce against a then-current supported AntennaPod release, identify whether media-type support, RSS parsing, HTML sanitization, or episode caching prevents discovery, and implement the smallest maintainable correction. A subscribed user must be able to discover and open the transcript after refresh while the existing `transcript.txt` URL/media type, stable episode GUID, idempotent rerun behavior, and other podcast clients remain compatible.
