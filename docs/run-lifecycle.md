# Run lifecycle and recovery

Run initialization is the first mutating workflow boundary. It validates the profile and configuration, resolves the profile-local episode date, claims the episode lease, and only then creates a run workspace.

## Initialize a run

Load the central environment described in [`setup.md`](setup.md), then run:

```bash
uv run python scripts/init_run.py \
  --profile examples/profiles/world-us-seattle-news.yaml
```

The command emits one compact JSON object. An owning invocation reports `"result":"initialized"` with its run directory. A simultaneous invocation for the same profile and local date exits successfully with `"result":"no_op"`, a null run ID/directory, and no new run artifacts.

The optional `AUDIO_ENGINE_MAX_RUN_AGE_SECONDS` setting controls stale recovery and defaults to 21,600 seconds (six hours). Values from 60 through 604,800 seconds are accepted. Set it longer than the expected gap between mutating workflow phases; every mutation verifies the run ID and refreshes the heartbeat.

## Durable layout and provenance

An initialized owner creates:

```text
<runtime-root>/
├── locks/
│   ├── episode-<sha256-of-episode-key>.json
│   └── feed-<sha256-of-feed-id>.lock
└── runs/<local-date>/<profile-id>/<run-id>/
    ├── collection-request.json
    ├── evidence-dossier.json                  # after valid collection
    ├── evidence-validation-attempt-1.json     # every first attempt
    ├── evidence-validation-attempt-2.json     # after one invalid attempt only
    ├── editorial-plan.json                    # after valid editorial planning
    ├── plan-validation-attempt-1.json         # every first plan attempt
    ├── plan-validation-attempt-2.json         # after one invalid plan only
    ├── episode-script.json                    # after valid scriptwriting
    ├── transcript.txt                         # exact accepted-turn projection
    ├── script-validation-attempt-1.json       # every first script attempt
    ├── script-validation-attempt-2.json       # after one invalid script only
    ├── tts/
    │   ├── manifest.json                      # ordered preparation contract
    │   ├── segment-001.json                   # exact transcript plus separate direction
    │   ├── audio/segment-001.pcm               # preserved provider response
    │   ├── audio/segment-001.wav               # validated intermediate audio
    │   └── ...
    ├── episode.mp3                            # validated final audio after assembly
    ├── show-notes.html                        # after successful publication
    ├── published-episode.json                 # after successful publication
    ├── state.json
    └── summary.md
```

The canonical episode key is `<profile-id>:<local-date>`. State records the profile/local date, profile/engine/skill/prompt versions, engine Git commit, observable models and collection method, collection/plan/script validation outcomes, TTS preparation inputs/manifest/segment count, timestamps, current and last valid stages, artifact paths/hashes, failure details, final-audio validity, and redacted publication locations. Phase provenance starts empty until its owning phase records an attempt.

Files are written to a private temporary sibling, synchronized, and atomically renamed. A stage advances only after its artifact validates on both sides of the write, its declared run identity and upstream references match current state, each referenced upstream file still exists and revalidates at its recorded SHA-256, and the new hash is recorded. State is authoritative if a machine failure leaves an unreferenced file between the artifact and state renames. An identical validated retry leaves the artifact/state unchanged but regenerates `summary.md`, repairing a transient summary-write failure.

## Stages and invalidation

PR 04 owns these transitions; later PRs add the remaining transition helpers:

| Valid artifact write | Current stage after write | Last completed valid stage |
| --- | --- | --- |
| Collection request | `collection` | `initialized` |
| Evidence dossier | `editorial` | `collection` |
| Editorial plan | `script` | `editorial` |
| Episode script | `tts` | `script` |
| Complete rendered segment set | `audio` | `tts` |
| Validated final MP3 | `publication` | `audio` |
| Verified conditional feed publication | `publication` | `publication` |

Replacing an artifact with identical validated bytes preserves state. A changed hash replaces that artifact, retains valid upstream references, rolls the run back to the owning validation stage, and removes all downstream references. Profile changes roll back to `initialized`; an accepted dossier replacement clears collection, plan, and script validation and returns to `collection`; an accepted plan replacement clears plan/script validation and returns to `editorial`; an accepted script replacement clears script validation and returns to `script`. Final-audio and publication status return to pending/not started whenever an invalidated dependency could affect them.

Collection method selection is recorded before retrieval. Failed optional capability names persist so reselection cannot loop back to a known failure. The first invalid dossier remains at `collection`, records a hashed validation report, and permits one focused repair or affected-step repeat. A second invalid attempt records its report, fails the run, and releases ownership. A valid attempt persists the normalized dossier only when every candidate uses a request-declared section, advances to `editorial`, records the valid report, and exposes dossier-size or section-target warnings in `summary.md`. A resume rechecks dossier/report hashes and returns `already_valid` without recollecting.

Editorial planning reads the complete valid dossier and profile. The first invalid plan remains at `editorial`, records a hashed report, and permits one focused repair; attempt 2 fails/releases. A valid attempt atomically persists the plan/report/state, advances to `script`, and surfaces target-shortfall warnings without turning profile targets into quotas. Resume rechecks plan/report and both input hashes before returning `already_valid`.

Scriptwriting reads the complete valid dossier, plan, and profile in a separate Codex phase. The first invalid script remains at `script`, records a hashed report, and permits one focused repair; attempt 2 fails/releases. A valid attempt atomically persists the script, exact transcript projection, report, and state, advances to `tts`, and surfaces nonfatal conversational warnings. Resume rechecks every input and output hash plus current lineage, profile policy, and transcript equality before returning `already_valid`.

TTS preparation remains at the `tts` stage because no audio has been rendered. It writes each versioned structured segment prompt atomically, writes the manifest last, then records the manifest/input hashes and segment count in state. State is authoritative if an interruption leaves unreferenced preparation files; a retry safely overwrites them. An unchanged rerun rechecks all hashes, speaker/voice consistency, estimates, ordering, and transcript reconstruction before returning `already_prepared` without rewriting valid files. Any changed accepted profile, dossier, plan, or script clears preparation and downstream audio/publication state.

TTS rendering also remains at `tts` until every manifest segment is complete. For each missing segment it preserves raw PCM, packages and decodes a WAV, then records hashes, audio parameters, duration, attempts, and completion time before requesting the next segment. Retry exhaustion records a resumable failure without releasing or discarding successful work. A rerun verifies every recorded file and starts with the first missing segment. The final success atomically changes the current stage to `audio` and the last completed valid stage to `tts`.

Final audio assembly runs only from the complete rendered prefix. It rechecks each exact ordered WAV with FFprobe and full decode, concatenates and encodes through bounded FFmpeg processes, validates the final mono 48 kHz MP3 against the summed segment duration, and atomically promotes `episode.mp3`. Only then are its hash and full validation metadata recorded and state advanced to `publication`. Failure records recovery guidance at `audio`, removes any publishable final reference, and preserves every rendered segment. An unchanged rerun at `publication` fully revalidates the MP3 and returns without rewriting it.

Publication revalidates that complete lineage and MP3 before any network mutation. It uploads and verifies all four episode assets before taking the feed lock and re-reading the current feed. The episode lease is always owned first; code never acquires an episode lease while holding the feed lock. Existing feeds use their latest ETag with `If-Match`, initial feeds use `If-None-Match: *`, and three conflicts cause resumable deferral rather than overwrite. Feed-lock timeout follows the same rule. Success leaves `current_stage` at `publication` for PR 12 finalization, advances `last_completed_valid_stage` to `publication`, and records only local artifact hashes plus redacted remote locations.

## Lease and failure recovery

- A current nonterminal owner causes a successful no-op. No run directory is selected, created, or mutated.
- Profile, Git, model, and initial-state validation completes in memory before lease acquisition, so preparation failure leaves neither a misleading live owner nor a partial workspace.
- A lease is recoverable when its validated owner state is terminal or its heartbeat is strictly older than the configured maximum age. Exact expiry remains live.
- A contender that observes the zero-byte `O_EXCL` creation window yields briefly and retries within the bounded acquisition loop; persistent empty leases still fail closed. Nonempty malformed records are never treated as recoverable.
- Recovery atomically renames the old record to a unique `.stale-...json` quarantine file, then retries exclusive creation. Do not manually delete quarantine evidence.
- A mutating helper holds the current lease's advisory lock from state read through artifact/state/summary persistence. Recovery waits for that critical section, then rechecks the replaced lease inode and refreshed heartbeat before deciding whether takeover is safe.
- Corrupt, oversized, mismatched, or unsafe lease records fail closed. Inspect the record and runtime filesystem; do not bypass ownership checks.
- Handled failures write redacted failure/recovery details to state and summary before releasing the lease. Unexpected crashes rely on stale recovery.
- Only the recorded run ID may refresh or release a lease. A non-owner must not edit state or remove a lock.

Run the repeatable lease/concurrency acceptance checks on macOS or Ubuntu:

```bash
uv run pytest -q \
  tests/unit/test_leases.py::test_live_lease_cannot_be_recovered_at_exact_expiry \
  tests/unit/test_leases.py::test_stale_lease_is_quarantined_before_new_owner \
  tests/integration/test_run_concurrency.py
uv run pytest -q -m "smoke and not live" tests/smoke/test_init_run.py
```

These use temporary roots, controlled clocks, synthetic profiles, and real processes/filesystem operations. They prove refusal before expiry, atomic quarantine after expiry, one owner/one artifact-free no-op for a shared episode key, one winner in a stale-recovery race, and independent owners for different keys.

PR 12 owns complete cross-invocation resume. Until then, a handled failure preserves its workspace and releases ownership, but a later initialization creates a new run rather than selecting that prior workspace. The explicit PR 12 acceptance test will require post-ownership selection of the prior run without changing valid upstream hashes or timestamps.

## Rollback

Stop any active run before rolling code back. A normal handled failure releases its lease; otherwise wait for the configured stale threshold and let the current code quarantine it. Preserve run directories and quarantine files for diagnosis. Reverting the PR 04 squash commit removes initialization and lifecycle mutation while retaining PR 03 read-only validators; it does not remove external runtime data automatically.
