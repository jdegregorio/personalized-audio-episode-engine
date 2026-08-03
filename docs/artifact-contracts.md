# Artifact contracts and validation

Pipeline handoffs are strict JSON files with `contract_version: "1.0"`. The Pydantic models in `audio_engine.artifacts` are the implementation source of truth; the matching committed JSON Schemas in [`schemas/`](../schemas/) are checked for exact drift in CI.

## Supported artifacts

| Validator type | Schema | Purpose |
| --- | --- | --- |
| `collection-request` | [`collection-request-v1.0.schema.json`](../schemas/collection-request-v1.0.schema.json) | Topic-generic section IDs/descriptions, audience/editorial context, evidence version, limits, capability hints, and output location |
| `evidence` | [`evidence-dossier-v1.0.schema.json`](../schemas/evidence-dossier-v1.0.schema.json) | Candidates, normalized claims, claim supports, source provenance, and collection method |
| `plan` | [`editorial-plan-v1.0.schema.json`](../schemas/editorial-plan-v1.0.schema.json) | Ordered candidate selection, claim requirements, treatment, exclusions, and host intent |
| `script` | [`episode-script-v1.0.schema.json`](../schemas/episode-script-v1.0.schema.json) | Two-speaker turns, claim lineage, planned-segment references, and TTS boundaries |
| `tts-manifest` | [`tts-manifest-v1.0.schema.json`](../schemas/tts-manifest-v1.0.schema.json) | Ordered prompt references, stable host/direction configuration, token limits, and exact turn coverage |
| `published-episode` | [`published-episode-v1.0.schema.json`](../schemas/published-episode-v1.0.schema.json) | Validated publication metadata and asset references; upload behavior arrives in PR 11 |
| `run-state` | [`run-state-v1.0.schema.json`](../schemas/run-state-v1.0.schema.json) | Minimal operational recovery state, provenance, artifact hashes, and publication outcome |

Unknown required versions fail with `unsupported_version`. JSON scalar types are strict, while ISO date and timezone-aware datetime strings retain their schema-defined parsing. Adding compatible optional fields requires an intentional model/schema update and contract tests; incompatible changes require a new contract version. PR 04 adds optional episode/engine provenance fields to v1.0 for compatibility, while every newly initialized run populates both and validates the episode key against the profile/local date.

## Evidence boundary

Every factual claim must resolve through a claim-support record to a source. Supports record `direct`, `attributed`, `inferred`, or `disputed` classification, an excerpt or precise locator, attribution/qualification data, and the source's originality/independence group. An excerpt may be omitted only for a retrievable primary source with a precise locator. Duplicate representations with the same locator or content hash cannot claim separate independence groups.

`published-episode` records the four public assets, stable GUID, enclosure metadata, duration, and current local lineage. Audio, transcript, and show-notes entries carry their exact content hashes. The `episode_metadata` entry uses `sha256: null` because embedding an object's own byte hash in those same bytes is self-referential; the publisher still verifies the uploaded metadata against its separately computed SHA-256 and state hash-binds the local `published-episode.json` artifact.

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

The single-artifact command enforces schema and dossier semantics. Reusable plan validators enforce complete candidate disposition, dossier/claim lineage, profile-defined sections and exclusion codes, host names, item/duration maxima, target shortfall warnings, and source-disagreement notes. Script validators trace every factual or analysis turn through plan, candidate, claim, support, and source; require planned coverage plus spoken attribution, qualifications, and disagreement; enforce configured speakers, voices, duration, TTS limits, and spoken-text safety; and report deterministic conversational-quality warnings.

During the production collection handoff, `record_collection.py` adapts every method to this same evidence boundary. It replaces method-supplied collection metadata with the selected method from state, binds the current collection-request hash, records collection prompt version `1.0.0`, and enforces the request's candidate/source/token limits and declared candidate sections before validation. It never rewrites claims, supports, sources, provenance, or research judgments.

Each attempt writes a private `evidence-validation-attempt-<n>.json` report and records its hash, counts, and repair status in run state. Attempt 1 may request one repair; attempt 2 is terminal when invalid. A valid dossier and its validation outcome are both required before the skill routes to editorial work.

During editorial recording, `record_editorial_plan.py` replaces agent-supplied provenance metadata with the active prompt/run/profile/date and current profile/dossier references. It preserves every editorial choice. Each attempt writes `plan-validation-attempt-<n>.json`; only a valid plan and matching report advance to script. The optional `profile` artifact reference is additive for v1.0 compatibility but is always populated and required by the production recorder.

During script recording, `record_script.py` similarly binds prompt/run/profile/date plus profile/dossier/plan references while preserving dialogue and structure. It writes `script-validation-attempt-<n>.json`, allows one repair, and generates `transcript.txt` as the exact ordered projection of the validated turns. The script records the transcript hash; verified resume rechecks all inputs, the script, transcript, and report before returning `already_valid`.

During TTS preparation, `prepare_tts.py` revalidates that accepted script boundary, recomputes conservative estimates for the complete provider input, and writes versioned structured prompts before the manifest and state reference. Manifest turn order and prompt transcript concatenation must exactly reconstruct the script and `transcript.txt`; prompt hashes, stable hosts/voices/direction, safe/absolute limits, and continuity metadata are verified on resume.

During rendering, `state.json.tts_rendering` records ordered successful segments with prompt/raw/WAV hashes, provider media type, PCM/WAV parameters, duration, attempt count, and completion time. Each success is durable before the next request. A failed status names only the missing segment and redacted recovery guidance; a complete status contains every manifest segment and advances to `audio`.

During assembly, `state.json.final_audio_validation` is valid only with the matching `artifacts.final_audio` reference and complete `audio/mpeg`/MP3, duration, sample-rate, channel, byte, and decode metadata. The canonical path is `episode.mp3`. A valid result advances to `publication`; an invalid result contains no publishable artifact reference and leaves the completed segment state intact for retry.

## Synthetic fixtures

[`tests/fixtures/artifacts/`](../tests/fixtures/artifacts/) contains one valid artifact of every supported type, including a TTS manifest, a copyright-safe RSS feed for later publication tests, and named JSON-pointer mutations for every required invalid evidence class. [`tests/fixtures/editorial-plans/`](../tests/fixtures/editorial-plans/) adds shorter-useful, optional-empty-section, source-disagreement, and arbitrary-taxonomy plans around the ordinary golden plan. [`tests/fixtures/scripts/`](../tests/fixtures/scripts/) defines compact balanced, imbalanced, disputed-source, arbitrary-topic, and malicious-text cases without duplicating the canonical script. The valid dossier is grounded in the committed corpus under [`tests/fixtures/sources/marine-brief/`](../tests/fixtures/sources/marine-brief/) and includes prompt-injection-looking text to prove it remains inert. `scripts/check_artifacts.py` validates schemas, every manifest expectation, baseline plan/script lineage, and the RSS structure in the secret-free integrity job; profile-aware plan, script, and TTS preparation behavior is covered by deterministic integration tests.
