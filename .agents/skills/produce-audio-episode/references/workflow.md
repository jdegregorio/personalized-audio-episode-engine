# Workflow

Run one profile from the repository root. Use the centrally configured environment; do not copy secrets into commands or artifacts.

## Initialize

```bash
uv run python scripts/doctor.py --profile <profile-path>
uv run python scripts/init_run.py --profile <profile-path>
```

Capture `run_directory` from the initializer's compact JSON. If `result` is `no_op`, stop successfully. For an owning run, inspect `<run-directory>/state.json` and `<run-directory>/summary.md`.

## Route by current stage

| Current stage | Action |
| --- | --- |
| `collection` | Load `evidence-collection.md`, select a method, create one dossier, and record validation. |
| `editorial` | Start a distinct phase, load `editorial-planning.md`, create one plan from the complete dossier and profile, and record validation. |
| `script` | Start a distinct phase, load `scriptwriting.md`, create one script from the complete dossier, plan, and profile, and record validation plus transcript projection. |
| `tts` without preparation | Load `tts-preparation.md` and prepare token-bounded manifest/prompt files from the accepted script. |
| `tts` with preparation | Load `tts-rendering.md` and render missing Gemini segments without repeating completed requests. |
| `audio` | Load `audio-assembly.md`, assemble and validate the final MP3 without creative processing. |
| `publication` | Load `publication.md`; upload and verify assets, then conditionally upsert the RSS feed last. |
| `finalized` | Do not improvise. Finalization arrives in its owning implementation PR. |
| failed/completed terminal state | Stop. Follow the recorded recovery guidance or report the completed result. |

After each deterministic command, read its compact JSON and then reload `state.json`. Do not infer success from a file's presence alone.

## Current implementation boundary

PR 11 ends after verified episode assets and a conditional RSS upsert record a published outcome while the run remains ready for finalization. Do not write dialogue in the editorial phase, synthesize speech in the script or preparation phase, add creative processing during assembly, or expose a feed item before every asset is publicly readable. Preserve valid final audio when publication defers or fails.
