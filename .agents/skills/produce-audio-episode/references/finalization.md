# Finalization

Every owning invocation ends by persisting terminal state before releasing its episode lease. Run finalization after successful publication, or when the invocation must stop and `state.json.status` is still `running`:

```bash
uv run python scripts/finalize_run.py --run <run-directory>
```

The command revalidates every referenced local artifact. A successful publication advances to `current_stage: finalized`, records `status: completed` and `completed_at`, regenerates the one-screen `summary.md`, then releases ownership. Its compact JSON contains only the run ID, local run/summary paths, episode key, and redacted publication labels.

If the workflow is incomplete, finalization records the current stage, a concise failure, and the exact resume command before releasing ownership. Valid dossiers, plans, scripts, completed TTS segments, and final audio remain unchanged. The command exits non-zero for this failed result; do not delete the workspace.

On the next invocation, run `init_run.py` with the same profile. `resumed` returns the same compatible workspace and prior run ID after ownership and hash validation. Then route from its restored stage. A completed run produces `no_op`; a second-invalid dossier, plan, or script is intentionally non-resumable and starts a fresh owning run.

Interpret successful finalization results as follows:

- `completed`: terminal success was persisted and the lease was released.
- `already_completed`: the completed state was unchanged; report its existing `summary.md`.

Never hand-edit terminal state or release a lease directly. Report the final user result from `summary.md`, which must state overall result, last valid stage, audio/publication outcomes, warnings, redacted locations, and recovery when applicable.
