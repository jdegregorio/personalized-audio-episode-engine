## Objective and traceability

<!-- State the objective and link the owning plan section plus PRD requirements/acceptance criteria. -->

## Scope

### In scope

-

### Explicit non-goals

-

## Risk, security, and privacy

<!-- Describe failure impact, secret/data exposure, external writes, and mitigations. Use "None" with rationale when appropriate. -->

## Changes and operational impact

- Dependencies:
- Configuration/environment variables:
- Schemas/artifacts/state transitions:
- External services/permissions:
- Rollback:

## Documentation impact

<!-- Name every exact documentation file reviewed, including unchanged files found accurate. -->

- Changed:
- Reviewed and unchanged:

## Automated test evidence

<!-- Include exact commands and concise results. Do not paste secrets, private URLs, runtime data, or current-news evidence. -->

- Unit:
- Contract/integration:
- Functional smoke:
- Coverage:
- Build/lint/type/integrity:
- GitHub Actions:

## Reviewer-facing UAT

<!-- Provide copy-pasteable steps and redacted user-visible evidence. -->

1.

Result:

## Correctness review

- Reviewer:
- Reviewed commit SHA:
- Requirements and failure paths inspected:
- Findings and changes made:
- Decision: `pass` / `changes requested`

## Simplification review

- Reviewer:
- Reviewed commit SHA:
- Full diff/stat/numstat inspected:
- Simplifications made:
- Retained complexity and concrete rationale:
- Documentation accuracy and conceptual surface reviewed:
- Decision: `pass` / `changes requested`

## Codex auto-review disposition

- [ ] Codex auto-review visibly completed for the final SHA.
- [ ] Every review comment/thread was examined.
- [ ] Actionable feedback was implemented and verified, or received a concrete recorded rationale.
- [ ] All threads are resolved or explicitly dismissed after rationale.
- [ ] No stale final-SHA review, pending change request, failed required check, or unresolved thread remains.

## Merge readiness

- [ ] Branch was created in a fresh worktree from the latest `origin/main`.
- [ ] Scope matches the owning PR in `plan.md`; unrelated changes are absent.
- [ ] Local and GitHub checks pass on the final reviewed SHA.
- [ ] UAT passed at the layer owned by this PR.
- [ ] Documentation and `docs/implementation-status.md` are current.
- [ ] No secret, private URL, runtime artifact, generated audio, or production evidence is committed.
- [ ] Squash merge and post-merge verification are ready.
