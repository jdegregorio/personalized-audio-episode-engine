# Run state

`state.json` is authoritative. Files that exist without a matching state reference are incomplete work, not completed stages.

## Collection, editorial, script, and TTS fields

- `collection_method` records native or specialized method type, name, and observable version.
- `prompt_versions.collection` records the collection instruction version.
- `collection_validation` records attempt 1 or 2, valid/invalid status, error and warning counts, whether one repair remains, and the hashed validation-report reference.
- `artifacts.collection_request`, `artifacts.evidence_dossier`, and `artifacts.evidence_validation` bind the current files by path and SHA-256.
- `prompt_versions.editorial` records editorial instruction version `1.0.0` after the first plan attempt.
- `plan_validation` records attempt, outcome counts, repair availability, and the hashed plan-validation report.
- `artifacts.editorial_plan` and `artifacts.plan_validation` bind the accepted plan and its report.
- `prompt_versions.script` records script instruction version `1.0.0` after the first script attempt.
- `script_validation` records attempt, outcome counts, repair availability, and the hashed script-validation report.
- `artifacts.episode_script`, `artifacts.transcript`, and `artifacts.script_validation` bind the accepted structured script, exact transcript projection, and report.
- `tts_preparation` binds the current script/transcript inputs, segment count, and hashed manifest.
- `artifacts.tts_manifest` binds the manifest; each manifest segment binds one ordered prompt file by path and SHA-256.
- `tts_rendering` records ordered successful segments with prompt/raw/WAV references, audio metadata, attempts, and timestamps; failed rendering names one resumable segment, while complete rendering contains every manifest segment.
- `final_audio_validation` records valid `audio/mpeg`/MP3, duration, sample rate, channels, bytes, and full-decode status only when its artifact exactly matches `artifacts.final_audio` at `episode.mp3`.
- `publication` records `not_started`, resumable `deferred`/`failed`, or `published` with redacted locations only. Published state requires hash-bound `artifacts.show_notes` and `artifacts.published_episode`; tokenized remote locations never enter state.

The recorder creates `evidence-validation-attempt-1.json` and, only after one invalid result, `evidence-validation-attempt-2.json`. Summary warnings expose dossier warning counts and invalid/repair status.

The editorial recorder uses the parallel `plan-validation-attempt-1.json` and optional attempt-2 report. A changed accepted dossier clears plan state; a changed accepted plan clears its old validation and returns the run to `editorial`.

The script recorder uses `script-validation-attempt-1.json` and an optional attempt-2 report. It generates `transcript.txt` from validated turns rather than accepting separate prose. A changed accepted plan clears script state; a changed accepted script clears its validation and returns the run to `script`.

The TTS preparer writes `tts/manifest.json` last after its atomic `tts/segment-<NNN>.json` prompt files, then records preparation in state. Unreferenced files after an interrupted write are incomplete and may be safely overwritten by a retry. Any accepted upstream change clears the preparation reference and all later audio/publication state.

The renderer writes raw PCM before WAV packaging and records each validated pair before continuing. A file without `tts_rendering.completed_segments` state is not successful work. Retry exhaustion keeps completed references unchanged and records the failed segment; final completion advances to `audio`.

The assembler validates all ordered WAVs, writes a temporary MP3, probes and fully decodes it, then atomically promotes `episode.mp3` before recording final state. A final file without `final_audio_validation.status: valid` and the matching `artifacts.final_audio` reference is incomplete work and must not be published.

## Resume rules

- At `collection` with no validation outcome, select/confirm the method and create the first dossier attempt.
- At `collection` with invalid attempt 1 and `repair_allowed: true`, make exactly one focused repair or affected-step repeat.
- At `editorial` with a valid collection outcome, do not recollect; use the collection recorder only when verifying `already_valid` is necessary.
- At `editorial` with no plan outcome, create the first plan from the complete profile and dossier.
- At `editorial` with invalid plan attempt 1 and `repair_allowed: true`, make exactly one focused repair.
- At `script` with a valid plan outcome, read the complete profile, dossier, and plan; create the first script without re-planning.
- At `script` with invalid script attempt 1 and `repair_allowed: true`, make exactly one focused repair.
- At `tts` with a valid script and no preparation state, run `prepare_tts.py` once; do not rewrite dialogue or contact a provider.
- At `tts` with valid preparation state, an unchanged rerun returns `already_prepared` only after rechecking every input, manifest, prompt, token estimate, speaker assignment, and transcript projection.
- At `tts` with valid preparation, run `render_audio.py`. A failed rendering resumes at `failed_segment_id`; never delete or rerender completed entries.
- At `audio` with complete rendering, an unchanged `render_audio.py` rerun returns `already_rendered` only after rechecking every raw/WAV hash and WAV parameter.
- At `audio`, run `assemble_audio.py`. A failed assembly preserves all rendered segments and remains at `audio`; correct the local tool/input issue and rerun without rendering again.
- At `publication`, an unchanged `assemble_audio.py` rerun returns `already_assembled` only after rechecking the MP3 hash, technical metadata, and full decode. Do not publish if that check rolls state back to `audio`.
- At `publication` with valid audio, run `publish_episode.py`. A deferred or failed publication reruns only this command; uploaded orphan assets are harmless and valid audio must remain unchanged. `already_published` still revalidates the assets and upserts exactly one stable GUID.
- After a command failure, inspect state. If it remains `running`, use `finalize_run.py` to persist terminal failure and release ownership; commands that already terminalized a second invalid dossier/plan/script need no extra mutation.
- On a later invocation, always reacquire through `init_run.py`. It returns `resumed` only after selecting the latest compatible failed/crash-interrupted workspace under ownership, preserving its run ID and validated files. Non-resumable validation exhaustion starts a new owning run; completed work returns `no_op`.
- At `publication` after `published` or `already_published`, run `finalize_run.py`. Completed state uses stage `finalized`, releases the lease, and is idempotent.

All state changes go through documented commands while the run owns the episode lease. Never hand-edit state, hashes, summaries, reports, or leases.
