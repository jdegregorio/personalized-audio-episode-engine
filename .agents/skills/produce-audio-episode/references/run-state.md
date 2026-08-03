# Run state

`state.json` is authoritative. Files that exist without a matching state reference are incomplete work, not completed stages.

## Collection fields

- `collection_method` records native or specialized method type, name, and observable version.
- `prompt_versions.collection` records the collection instruction version.
- `collection_validation` records attempt 1 or 2, valid/invalid status, error and warning counts, whether one repair remains, and the hashed validation-report reference.
- `artifacts.collection_request`, `artifacts.evidence_dossier`, and `artifacts.evidence_validation` bind the current files by path and SHA-256.

The recorder creates `evidence-validation-attempt-1.json` and, only after one invalid result, `evidence-validation-attempt-2.json`. Summary warnings expose dossier warning counts and invalid/repair status.

## Resume rules

- At `collection` with no validation outcome, select/confirm the method and create the first dossier attempt.
- At `collection` with invalid attempt 1 and `repair_allowed: true`, make exactly one focused repair or affected-step repeat.
- At `editorial` with a valid collection outcome, run the recorder only to verify `already_valid`; do not recollect.
- In a failed state, stop and use the recorded recovery guidance. Do not acquire or mutate the released workspace manually.

All state changes go through documented commands while the run owns the episode lease. Never hand-edit state, hashes, summaries, reports, or leases.
