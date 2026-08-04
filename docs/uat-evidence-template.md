# Redacted MVP UAT evidence

Copy this template into the PR or release record. Do not commit completed production evidence to the repository. Replace placeholders with concise results, not raw logs.

## Candidate

- Reviewed commit: `<sha>`
- Stable qualification checkout: `<redacted stable path label>`
- Profile: `world-us-seattle-news`
- Schedule/timezone: `daily 07:00 America/Los_Angeles`
- Model/reasoning: `<configured non-secret values>`
- Source/dependency/schema/profile changes during streak: `none`

## Automated gates

- Local build/integrity/lint/type: `<pass/fail and concise counts>`
- Deterministic tests/coverage: `<pass/fail, count, percent>`
- Functional smoke: `<pass/fail and count>`
- Configured doctor: `<pass/fail>`
- Required PR checks: `<pass/fail and count>`
- Release-candidate workflow on merged `main`: `<run link and pass/fail>`

## Scheduled streak

| Run | Scheduled date | Redacted run ID | Audio validation | Publication | Finalization | Intervention |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `<YYYY-MM-DD>` | `<suffix or redacted ID>` | `<duration/format/pass>` | `<published/already-published/failure>` | `<completed/failed>` | `none` |
| 2 | `<YYYY-MM-DD>` | `<suffix or redacted ID>` | `<duration/format/pass>` | `<published/already-published/failure>` | `<completed/failed>` | `none` |
| 3 | `<YYYY-MM-DD>` | `<suffix or redacted ID>` | `<duration/format/pass>` | `<published/already-published/failure>` | `<completed/failed>` | `none` |

Streak decision: `<pass/fail; failures restart at run 1>`

## Device and public-delivery UAT

- AntennaPod refresh/discovery/stream/download/playback: `<pass/fail>`
- Two distinguishable contributing speakers: `<human-confirmed pass/fail>`
- In-app description: `<pass/fail>`
- Web/globe HTML notes and transcript link: `<pass/fail>`
- Independent transcript response: `<status and media type only>`
- Audio/show-notes/metadata responses: `<status and media types only>`
- Feed response/cache behavior/transcript element: `<redacted pass/fail>`
- Same-day idempotent item count: `<before/after counts>`

## Recovery and concurrency

- Failed-segment resume: `<preserved segment evidence and pass/fail>`
- Publication-only resume: `<unchanged audio hash/size/mtime pass/fail; do not paste hash>`
- Same-key initialization: `<one owner/one no-op/no second workspace pass/fail>`
- Different-key and external-ETag publication: `<all items retained pass/fail>`

## Acceptance summary

| Criteria | Evidence | Result |
| --- | --- | --- |
| AC-001–003 | Generic profile/collection/repository audit | `<pass/fail>` |
| AC-004–011 | Scheduled workflow and persisted grounded artifacts | `<pass/fail>` |
| AC-012–014 | Human playback, segmentation, retry | `<pass/fail>` |
| AC-015–018 | R2/AntennaPod, idempotency, summary, reproducible setup | `<pass/fail>` |
| AC-019 | Three consecutive scheduled runs | `<pass/fail>` |
| AC-020 | Initialization and publication concurrency | `<pass/fail>` |

Overall MVP decision: `<approve/reject>`

Open post-MVP items: `AntennaPod native transcript-pane discoverability; see plan.md`
