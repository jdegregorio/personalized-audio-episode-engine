# Operations

The engine supports validated environment/profile preflight, deterministic artifact/lineage validation, owner-checked run initialization/resume, capability-neutral evidence collection, profile-driven editorial planning, grounded two-host scriptwriting, token-bounded TTS preparation/rendering, validated FFmpeg assembly, conditional Cloudflare R2 podcast publication, and terminal finalization.

## Development gate

Run from the active feature worktree:

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

The `not live and not smoke` suite is deterministic and must not read the owner's real environment file or access a network service. Smoke tests prove user-visible behavior at the smallest useful boundary. Live tests remain explicit and use the narrow `live-smoke` environment only after their implementation PR.

## Environment preflight

Load the owner-managed environment as described in [`setup.md`](setup.md), then run:

```bash
uv run python scripts/doctor.py --profile examples/profiles/world-us-seattle-news.yaml
```

`PASS` means local configuration and tools are structurally ready; it is not a live Gemini or R2 probe. A `FAIL` line names the setting, tool, root, profile, or required capability the operator must fix without echoing its value.

## Artifact validation

Validate one JSON artifact through the public contract boundary:

```bash
uv run python scripts/validate_artifact.py --type evidence --input <artifact-path>
```

Fatal validation writes a concise JSON result to stderr and exits non-zero. Pass `--report <report-path>` to persist the complete validation result for a repair; the report path may not overwrite the input. Filesystem source locators require one or more explicit `--allowed-input-root <path>` arguments. See [`artifact-contracts.md`](artifact-contracts.md) for supported types and the boundary between structural validation and later phase policy.

## Run initialization

After loading the central environment, acquire ownership and create the collection request, state, and summary:

```bash
uv run python scripts/init_run.py \
  --profile examples/profiles/world-us-seattle-news.yaml
```

The command returns compact JSON for `initialized`, `resumed`, or `no_op`. Resume selection occurs only after exclusive ownership and returns the prior compatible run ID/directory after validating every referenced file. `no_op` creates no workspace when another owner is live and returns no completed same-day episode for mutation. See [`run-lifecycle.md`](run-lifecycle.md) for the layout, state transitions, invalidation rules, concurrency UAT, stale recovery, and rollback procedure.

## Evidence collection

Follow the production [skill](../.agents/skills/produce-audio-episode/SKILL.md). After inspecting available capabilities, record either an already available suitable capability or native public-web fallback:

```bash
uv run python scripts/select_collection_method.py --run <run-directory>
```

The agent writes one dossier to the generated request's `output_path`, then records it:

```bash
uv run python scripts/record_collection.py --run <run-directory>
```

The recorder binds current request lineage, selected method, prompt version, and configured limits; validates and persists the dossier; writes a hashed validation report; and advances only valid evidence. It returns `repair_required` once, fails/releases after a second invalid attempt, and returns `already_valid` when resuming verified collection. See [`optional-collectors.md`](optional-collectors.md) and [`troubleshooting.md`](troubleshooting.md).

## Editorial planning

In a distinct Codex phase, follow the skill's [`editorial-planning.md`](../.agents/skills/produce-audio-episode/references/editorial-planning.md) reference. Read the complete profile and validated dossier, write `<run-directory>/editorial-plan.json`, and run:

```bash
uv run python scripts/record_editorial_plan.py --run <run-directory>
```

The command authoritatively binds prompt/run/profile/date and profile/dossier hashes, then validates selected and excluded candidates, claims, order, section and item limits, duration, configured lead hosts, profile-defined reason codes, transitions, and useful disagreement notes. Profile minimum counts remain editorial targets: a shortfall is a warning, while maxima and duration bounds fail. Attempt 1 may receive one repair; attempt 2 fails/releases. A verified resume returns `already_valid` without re-planning.

## Scriptwriting

In a distinct Codex phase, follow the skill's [`scriptwriting.md`](../.agents/skills/produce-audio-episode/references/scriptwriting.md) reference. Read the complete profile, dossier, and plan, write `<run-directory>/episode-script.json`, and run:

```bash
uv run python scripts/record_script.py --run <run-directory>
```

The command authoritatively binds prompt/run/profile/date and current input hashes, validates planned claim coverage through underlying sources, preserves required spoken attribution/qualifications/disagreement, enforces two configured hosts and spoken-text policy, and surfaces balance/performance warnings. It writes `transcript.txt` only from validated ordered turns. Attempt 1 may receive one repair; attempt 2 fails/releases. A verified resume returns `already_valid` after rechecking inputs, script, transcript, and report.

## TTS preparation

At `tts`, follow the skill's [`tts-preparation.md`](../.agents/skills/produce-audio-episode/references/tts-preparation.md) reference and run:

```bash
uv run python scripts/prepare_tts.py --run <run-directory>
```

The command revalidates the accepted script/transcript, rejects an unknown provider/model capability or unsafe token configuration, packs natural boundaries toward two-to-four-minute segments, and refuses a spoken turn that cannot fit. It writes private atomic `tts/segment-<NNN>.json` prompts followed by `tts/manifest.json` and state. The manifest records prompt hashes, token estimates, stable speakers/voices/direction, and exact ordered turn coverage. An unchanged rerun returns `already_prepared` without rewriting valid outputs. No provider is contacted.

## Gemini rendering

With a valid preparation, follow the skill's [`tts-rendering.md`](../.agents/skills/produce-audio-episode/references/tts-rendering.md) reference and run:

```bash
uv run python scripts/render_audio.py --run <run-directory>
```

The command sends one bounded request at a time and disables the SDK's independent retries. It retries a failed response up to three times near 2, 5, and 12 seconds, saves raw PCM before local WAV packaging, verifies duration/format/decode health, and records every successful segment before continuing. Exhaustion remains resumable at the named segment; an unchanged complete rerun contacts no provider. Only a complete set advances state to `audio`.

## Final audio assembly

At `audio`, follow the skill's [`audio-assembly.md`](../.agents/skills/produce-audio-episode/references/audio-assembly.md) reference and run:

```bash
uv run python scripts/assemble_audio.py --run <run-directory>
```

The command rechecks every manifest-ordered WAV, runs bounded FFprobe and full-decode checks, concatenates without creative processing, and encodes a 96 kbps mono 48 kHz MP3. It validates codec/container, duration against the sum of segments, sample rate, channel count, bytes, and complete decode before atomically promoting `episode.mp3` and advancing to `publication`. `already_assembled` means the recorded hash and all technical validation fields were rechecked without rewriting the file. Failure stays resumable at `audio`; rerun the same command after correcting FFmpeg/FFprobe or the named segment-file issue.

## R2 probe and episode publication

Before the first live publication, verify the configured bucket, S3 credential, public endpoint, media type, and cleanup with one random non-sensitive object:

```bash
uv run python scripts/smoke_r2.py
```

The probe uses `probes/`, never the feed token, and deletes the object in the same invocation. It does not inspect lifecycle configuration or publish a feed. After a valid final MP3, follow the skill's [`publication.md`](../.agents/skills/produce-audio-episode/references/publication.md) reference and run:

```bash
uv run python scripts/publish_episode.py --run <run-directory>
```

The publisher fully revalidates final audio, writes deterministic HTML notes and JSON metadata, then uploads MP3, transcript, notes, and metadata with explicit content/cache metadata. Every asset must match S3 HEAD and a complete public GET before the RSS item can be exposed. While the episode lease remains owned, the publisher takes the bounded `feed-<sha256-feed-id>.lock`, reads the latest feed and ETag, prunes entries at or before the configured expiry boundary, upserts the stable GUID, validates the merged RSS, and writes it last with `If-Match` or `If-None-Match: *`. Success is recorded only after S3 HEAD/read and a complete public GET also verify the winning feed revision.

`deferred` exits `2` and means the lock or three conditional attempts did not converge. Rerun only publication; valid audio and harmless orphan assets are retained. `already_published` is a successful verified same-day upsert, not a duplicate.

## Finalization and resume

After `published`/`already_published`, or when an owning invocation must stop while state remains `running`, run:

```bash
uv run python scripts/finalize_run.py --run <run-directory>
```

The command validates recorded local artifacts before terminal success, writes `state.json` and the one-screen `summary.md`, then releases the episode lease. Successful publication becomes `status: completed` at `current_stage: finalized`. Incomplete work becomes `status: failed` with its last valid stage and one exact recovery command; it exits non-zero but preserves valid artifacts. Run `init_run.py` with the same profile in a later invocation: `resumed` restores that same compatible run ID/directory, while non-resumable second-invalid dossier/plan/script failures intentionally start a new run.

Read the user-facing outcome from `summary.md`. It reports audio/publication status, warnings, local output directory, redacted publication labels, and recovery without exposing a tokenized URL.

## Scheduled production

Configure the standalone daily Codex task with the exact prompt, local environment, model guidance, independent-context rule, and stable-checkout qualification procedure in [`scheduled-task.md`](scheduled-task.md). Use [`release-checklist.md`](release-checklist.md) for the three-run, device, idempotency, recovery, concurrency, promotion, and tag gates. Do not introduce an operating-system cron wrapper or an all-in-one production command.

## Production invariants

- One independent Codex run processes one profile.
- Files are the system of record; a stage advances only after durable validation.
- Use only documented repository commands. A production run never writes ad hoc source code.
- Production runs do not modify tracked code, dependencies, schemas, profiles, or documentation.
- Resume valid work rather than rerunning successful external operations.
- Persist terminal state through `finalize_run.py` before intentionally ending an owning invocation.
- Never log credentials, tokenized object keys, or complete feed URLs.
- Default CI cannot synthesize speech or publish objects because it receives no production secrets.

## Rollback at this phase

`render_audio.py` contacts Gemini and `publish_episode.py` contacts R2. If an invocation must stop, finalize its running state first; validated local artifacts remain authoritative and the next initializer can reacquire them. A publication interruption may leave episode objects that are not referenced by the feed; let the `episodes/` lifecycle rule remove them and rerun publication without touching audio. Never manually overwrite `feed.xml`, delete a live lock, or edit state.

Service-specific recovery and rotation are documented in [`cloudflare-r2.md`](cloudflare-r2.md).
