# Artifact contracts and validation

Pipeline handoffs are strict JSON files with `contract_version: "1.0"`. The Pydantic models in `audio_engine.artifacts` are the implementation source of truth; the matching committed JSON Schemas in [`schemas/`](../schemas/) are checked for exact drift in CI.

## Supported artifacts

| Validator type | Schema | Purpose |
| --- | --- | --- |
| `collection-request` | [`collection-request-v1.0.schema.json`](../schemas/collection-request-v1.0.schema.json) | Topic-generic scope, audience/editorial context, evidence version, limits, capability hints, and output location |
| `evidence` | [`evidence-dossier-v1.0.schema.json`](../schemas/evidence-dossier-v1.0.schema.json) | Candidates, normalized claims, claim supports, source provenance, and collection method |
| `plan` | [`editorial-plan-v1.0.schema.json`](../schemas/editorial-plan-v1.0.schema.json) | Ordered candidate selection, claim requirements, treatment, exclusions, and host intent |
| `script` | [`episode-script-v1.0.schema.json`](../schemas/episode-script-v1.0.schema.json) | Two-speaker turns, claim lineage, planned-segment references, and TTS boundaries |
| `published-episode` | [`published-episode-v1.0.schema.json`](../schemas/published-episode-v1.0.schema.json) | Validated publication metadata and asset references; upload behavior arrives in PR 11 |
| `run-state` | [`run-state-v1.0.schema.json`](../schemas/run-state-v1.0.schema.json) | Minimal operational recovery state, provenance, artifact hashes, and publication outcome |

Unknown required versions fail with `unsupported_version`. JSON scalar types are strict, while ISO date and timezone-aware datetime strings retain their schema-defined parsing. Adding compatible optional fields requires an intentional model/schema update and contract tests; incompatible changes require a new contract version. PR 04 adds optional episode/engine provenance fields to v1.0 for compatibility, while every newly initialized run populates both and validates the episode key against the profile/local date.

## Evidence boundary

Every factual claim must resolve through a claim-support record to a source. Supports record `direct`, `attributed`, `inferred`, or `disputed` classification, an excerpt or precise locator, attribution/qualification data, and the source's originality/independence group. An excerpt may be omitted only for a retrievable primary source with a precise locator. Duplicate representations with the same locator or content hash cannot claim separate independence groups.

Source material is untrusted inert data. Validation parses JSON and compares values only; it does not import code, follow source instructions, invoke a shell, download a locator, or modify the input. Excerpts are capped at 1,000 characters to keep fixtures and dossiers focused rather than archiving articles.

Canonical locators may be ordinary web URLs, generic resource URIs such as `connector://...`, or absolute filesystem paths. Unsafe schemes, malformed ports, embedded URL credentials, relative/traversal paths, and filesystem paths outside explicit allowed roots fail. Filesystem locators require `--allowed-input-root`; the validator never infers a broad root.

## Command and reports

```bash
uv run python scripts/validate_artifact.py \
  --type evidence \
  --input tests/fixtures/artifacts/valid/evidence-dossier.json
```

Success emits concise JSON on stdout. Fatal errors emit concise JSON on stderr and exit non-zero. Each issue has a stable code, exact JSON-pointer path, and safe message. Use `--report <path>` for the full repair report; the command rejects a report path that would overwrite the input.

Collection requests also require one or more explicit `--allowed-output-root` values. The request's `output_path` must resolve below one of those run/runtime roots; the validator never trusts absoluteness alone.

The single-artifact command enforces schema and dossier semantics. Reusable `validate_plan_against_dossier` and `validate_script_against_plan_and_dossier` hooks enforce cross-artifact references and factual lineage. PRs 06 and 07 add profile-aware duration/section/host policy and prose-quality warnings without changing this baseline contract.

## Synthetic fixtures

[`tests/fixtures/artifacts/`](../tests/fixtures/artifacts/) contains one valid artifact of every supported type, a copyright-safe RSS feed for later publication tests, and named JSON-pointer mutations for every required invalid evidence class. The mutations keep each failure explicit without copying the full golden dossier for every case. The valid dossier deliberately includes both web and connector locators plus prompt-injection-looking text to prove it remains inert. `scripts/check_artifacts.py` validates schemas, every manifest expectation, plan/script lineage, and the RSS structure in the secret-free integrity job.
