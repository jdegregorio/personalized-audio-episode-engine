# MVP release checklist

Use this checklist for PR 13 and the final `main` release. Evidence belongs in the pull request or a secret-free GitHub artifact using [`uat-evidence-template.md`](uat-evidence-template.md); generated runtime output does not belong in Git.

## Candidate freeze and automated gates

- [ ] The PR 13 worktree has a stable path, an empty `git status --short`, and one recorded commit SHA for the entire qualification streak.
- [ ] `uv sync --locked --all-extras --dev`, `uv lock --check`, build, isolated Python 3.12 wheel import, repository/artifact checks, Ruff, Pyright, deterministic tests at 85% or greater coverage, and smoke tests pass.
- [ ] The configured doctor passes for `examples/profiles/world-us-seattle-news.yaml`.
- [ ] Required pull-request checks pass on the reviewed SHA.
- [ ] Correctness and simplification passes cover the complete final diff.
- [ ] No dependency, schema, profile, service, or production configuration expansion is hidden in the release PR.

## Scheduled qualification

- [ ] The standalone Codex task uses the exact prompt and settings in [`scheduled-task.md`](scheduled-task.md).
- [ ] A fresh-context manual invocation passes before recurrence is enabled.
- [ ] Scheduled run 1 produces and validates a playable MP3 without intervention.
- [ ] Scheduled run 2 does the same on the next scheduled date without an intervening change.
- [ ] Scheduled run 3 does the same on the next scheduled date without an intervening change.
- [ ] Each run ends in a terminal state and its `summary.md` alone communicates result, stage, audio/publication status, warnings, redacted locations, and recovery when applicable.
- [ ] The checkout remains byte-for-byte unchanged for tracked source, dependencies, schemas, profiles, and documentation throughout the streak.

## User-visible and recovery acceptance

- [ ] The latest episode has two stable, distinguishable speakers and both contribute materially.
- [ ] AntennaPod refreshes the private RSS address, discovers the latest item, streams it, downloads it, and plays it.
- [ ] The in-app description is present; the episode web/globe action opens the full HTML notes and their transcript link.
- [ ] The plain-text transcript resolves independently. A separate native AntennaPod transcript pane is tracked post-MVP and is not a release gate.
- [ ] Public feed, audio, transcript, show-notes, and metadata responses have the expected status and media types; the feed is no-cache and assets use the documented cache policy.
- [ ] A same-day rerun updates/verifies the stable item instead of creating a duplicate.
- [ ] A publication-only retry preserves the validated audio hash, size, and modification time.
- [ ] A failed-segment retry preserves completed segment hashes and modification times.
- [ ] Same-key concurrent initialization produces one owner and one successful no-op without a second workspace.
- [ ] Different-key/local-feed concurrency and a simulated external ETag race preserve every feed item.

## Security and operations

- [ ] Evidence contains no credential, feed token, complete private URL, tokenized object key, current-news artifact, transcript, or generated audio.
- [ ] The runtime credential is bucket-scoped object read/write only; production code performs no Cloudflare administration.
- [ ] Runtime and staging roots remain outside the checkout with their documented permissions.
- [ ] Rollback is understood: disable the task; finalize/retry valid work; rotate credentials or feed URL only when exposure requires it.

## Merge, promotion, and tag

- [ ] PR 13 is squash-merged only after its local, CI, UAT, recovery, concurrency, and three-run gates pass.
- [ ] The stable primary checkout is fast-forwarded to merged `main` and passes the complete post-merge gate.
- [ ] The `Release candidate` workflow passes on `main` and its secret-free report is retained.
- [ ] The scheduled task now targets the stable primary checkout with the approved prompt/settings and is active.
- [ ] The PR 13 worktree and branch are removed only after schedule promotion.
- [ ] The approved merged commit is tagged `v0.1.0`; the tag is pushed after all prior boxes pass.
