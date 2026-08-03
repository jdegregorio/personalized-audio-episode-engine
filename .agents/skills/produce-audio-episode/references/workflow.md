# Workflow

Run one profile from the repository root. Use the centrally configured environment; do not copy secrets into commands or artifacts.

## Initialize

```bash
uv run python scripts/doctor.py --profile <profile-path>
uv run python scripts/init_run.py --profile <profile-path>
```

Capture `run_directory` from the initializer's compact JSON. If `result` is `no_op`, stop successfully. `resumed` means the initializer reacquired the same compatible workspace and run ID after validating persisted artifacts; do not create a replacement. For any owning result, inspect `<run-directory>/state.json` and `<run-directory>/summary.md`.

## Route by current stage

| Current stage | Action |
| --- | --- |
| `collection` | Load `evidence-collection.md`, select a method, create one dossier, and record validation. |
| `editorial` | Start a distinct phase, load `editorial-planning.md`, create one plan from the complete dossier and profile, and record validation. |
| `script` | Start a distinct phase, load `scriptwriting.md`, create one script from the complete dossier, plan, and profile, and record validation plus transcript projection. |
| `tts` without preparation | Load `tts-preparation.md` and prepare token-bounded manifest/prompt files from the accepted script. |
| `tts` with preparation | Load `tts-rendering.md` and render missing Gemini segments without repeating completed requests. |
| `audio` | Load `audio-assembly.md`, assemble and validate the final MP3 without creative processing. |
| `publication` | Load `publication.md`; upload and verify assets, then conditionally upsert the RSS feed last. After `published`/`already_published`, load `finalization.md`. |
| `finalized` | Read `summary.md` and return its concise completed result; do not repeat prior stages. |
| failed/completed terminal state | Stop. Follow the recorded recovery guidance or report the completed result. |

After each deterministic command, read its compact JSON and then reload `state.json`. Do not infer success from a file's presence alone.

## Invocation boundary

Do not write dialogue in the editorial phase, synthesize speech in the script or preparation phase, add creative processing during assembly, or expose a feed item before every asset is publicly readable. Preserve valid final audio when publication defers or fails. Before ending an owning invocation, load `finalization.md`: complete a published run, or persist an actionable failure if state is still `running`, so ownership is never abandoned intentionally.
