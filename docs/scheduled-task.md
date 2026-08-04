# Scheduled production task

The MVP uses one standalone Codex scheduled task. Codex supplies research and editorial judgment; the repository skill and documented commands supply validation, state, audio, publication, and recovery. There is no daemon, queue, wrapper CLI, or direct OpenAI API runner.

## Canonical task prompt

Copy this prompt without adding source-editing or alternate orchestration instructions.

<!-- scheduled-task-prompt:start -->

```text
Use $produce-audio-episode to generate and publish today's episode using
examples/profiles/world-us-seattle-news.yaml.

Run the workflow from the repository root. Use America/Los_Angeles as the
episode timezone. Use the best available research skills or tools that satisfy
the profile. If no suitable specialized capability is installed, perform native
web research. Use the repository's schemas, prompts, documented commands, and
reusable scripts.

Load the owner-managed environment from
/Users/jdegregorio/.config/personalized-audio-episode-engine/secrets.env without
printing its values or copying it into the checkout.

Do not modify application source code, dependencies, schemas, profile
configuration, or tracked documentation during this production run. Resume an
incomplete run for the same profile and date when valid artifacts already exist.
Publish only after all required validations and audio checks pass. End an owning
invocation with terminal finalization, then return the contents of the final
human-readable run summary.
```

<!-- scheduled-task-prompt:end -->

The prompt intentionally delegates stage routing to [`$produce-audio-episode`](../.agents/skills/produce-audio-episode/SKILL.md). Do not paste the stage instructions into the task or replace the skill with an ad hoc script.

## Codex task configuration

Configure these fields in the Codex desktop scheduler:

| Field | MVP value |
| --- | --- |
| Kind | Standalone recurring task; every occurrence starts a new independent context |
| Project | The checkout being qualified; after release, the stable primary checkout |
| Execution | Local project, workspace-write access, network enabled |
| Schedule | Daily at 07:00 in `America/Los_Angeles` |
| Model | GPT-5.6 Sol, or the highest-capability configurable GPT-5.6 model available |
| Reasoning | High enough for source-grounded research and editorial work; `xhigh` is the MVP setting |
| Environment | The canonical prompt loads `/Users/jdegregorio/.config/personalized-audio-episode-engine/secrets.env` without printing it |
| Notifications | Failed runs only; inspect all three qualification results directly |

Grant only access to the selected checkout, the configured runtime/staging roots, outbound HTTPS/DNS, and the owner-managed environment file. The task does not need inbound networking, a Cloudflare administrative token, an OpenAI API key, a database, or access to unrelated repositories.

The computer must remain powered on and awake, the Codex desktop app must remain signed in and running, and the selected checkout plus configured runtime paths must remain available at the scheduled time.

## Release-candidate qualification

1. Keep the PR 13 worktree at one stable path and exact commit for the entire streak. Do not use it for other work.
2. Run the complete local gate and configured doctor from that checkout. Confirm `git status --short` is empty.
3. Configure the task above against that local checkout and environment file. Run the canonical prompt once manually in a fresh context before enabling the recurrence.
4. Enable the daily schedule. Do not edit code, dependencies, schemas, profiles, documentation, task prompt, model setting, environment, or runtime artifacts between qualification runs.
5. Require three consecutive scheduled dates to produce a newly validated playable MP3 without manual intermediate intervention. A failed or manually repaired run breaks the streak; fix the smallest owning defect and restart at run 1.
6. Record only the redacted fields in [`uat-evidence-template.md`](uat-evidence-template.md). Never record a complete feed URL, tokenized object key, credential, current-news dossier, transcript, generated audio, or private runtime artifact.
7. Perform the AntennaPod, idempotency, recovery, and concurrency checks in [`release-checklist.md`](release-checklist.md) before merge.

`no_op` is correct for a same-day repeat or a live owner, but it does not count as one of the three newly produced qualification episodes.

## Promotion to the stable checkout

After PR 13 is squash-merged and the merged commit passes the complete local gate:

1. Manually dispatch the `Release candidate` workflow on `main` and retain its secret-free validation report.
2. Update the scheduled task's project checkout from the retained PR 13 worktree to the stable primary checkout. Preserve the prompt, schedule, model, reasoning setting, environment file, and notification policy.
3. Confirm the task is active and the primary checkout is clean at the approved commit.
4. Remove the PR worktree only after that confirmation.
5. Create the annotated MVP tag only after the three-run evidence, final device UAT, merged-main checks, and release-candidate workflow all pass.

## Failure and rollback

If an invocation owns a run but cannot complete, it must call `uv run python scripts/finalize_run.py --run <run-directory>` so the next invocation can resume valid artifacts. Do not edit `state.json`, delete a lease, rerender valid audio, or overwrite the feed manually.

To stop production, disable the scheduled task. If access must also be revoked, rotate the Gemini/R2 credentials or feed token as described in [`cloudflare-r2.md`](cloudflare-r2.md). Disabling the task does not remove local run evidence or already published objects.
