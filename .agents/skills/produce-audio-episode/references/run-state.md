# Run state

`state.json` is authoritative. Files that exist without a matching state reference are incomplete work, not completed stages.

## Collection and editorial fields

- `collection_method` records native or specialized method type, name, and observable version.
- `prompt_versions.collection` records the collection instruction version.
- `collection_validation` records attempt 1 or 2, valid/invalid status, error and warning counts, whether one repair remains, and the hashed validation-report reference.
- `artifacts.collection_request`, `artifacts.evidence_dossier`, and `artifacts.evidence_validation` bind the current files by path and SHA-256.
- `prompt_versions.editorial` records editorial instruction version `1.0.0` after the first plan attempt.
- `plan_validation` records attempt, outcome counts, repair availability, and the hashed plan-validation report.
- `artifacts.editorial_plan` and `artifacts.plan_validation` bind the accepted plan and its report.

The recorder creates `evidence-validation-attempt-1.json` and, only after one invalid result, `evidence-validation-attempt-2.json`. Summary warnings expose dossier warning counts and invalid/repair status.

The editorial recorder uses the parallel `plan-validation-attempt-1.json` and optional attempt-2 report. A changed accepted dossier clears plan state; a changed accepted plan clears its old validation and returns the run to `editorial`.

## Resume rules

- At `collection` with no validation outcome, select/confirm the method and create the first dossier attempt.
- At `collection` with invalid attempt 1 and `repair_allowed: true`, make exactly one focused repair or affected-step repeat.
- At `editorial` with a valid collection outcome, do not recollect; use the collection recorder only when verifying `already_valid` is necessary.
- At `editorial` with no plan outcome, create the first plan from the complete profile and dossier.
- At `editorial` with invalid plan attempt 1 and `repair_allowed: true`, make exactly one focused repair.
- At `script` with a valid plan outcome, run the editorial recorder only to verify `already_valid`; do not re-plan.
- In a failed state, stop and use the recorded recovery guidance. Do not acquire or mutate the released workspace manually.

All state changes go through documented commands while the run owns the episode lease. Never hand-edit state, hashes, summaries, reports, or leases.
