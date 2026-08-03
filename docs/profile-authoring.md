# Episode-profile authoring

Episode profiles are topic-specific YAML data validated before any run output is created. The engine understands generic sections and limits; it does not contain world, U.S., Seattle, news, sports, publisher, or taxonomy rules.

## Start from the example

Copy [`world-us-seattle-news.yaml`](../examples/profiles/world-us-seattle-news.yaml) to an allowed input root and change the data. Keep `schema_version: "1.0"` quoted. The authoritative machine-readable contract is [`episode-profile-v1.0.schema.json`](../schemas/episode-profile-v1.0.schema.json).

The main groups are:

- `identity` for feed identity and a title template containing `{date}`.
- `episode` and `audience` for the topic, arbitrary section IDs, exclusions, timezone, locale, and preferences.
- `collection` for source types, suggested or explicitly required capabilities, time window, generic candidate targets, and dossier warning/hard token limits.
- `editorial` for duration/item bounds, section targets, empty-section policy, and topic-specific policy data.
- `hosts`, `performance`, and `tts` for the two recurring speakers and provider-neutral preparation limits.
- `publishing` for feed metadata and environment-variable names. Never put an endpoint, bucket, public URL, token, retention value, or credential directly in a profile.

Every key is validated and unknown keys fail closed. Section IDs may be any lowercase identifier, but all candidate targets, editorial targets, and allowed-empty references must name a declared section. `required_capabilities` is a hard preflight requirement; `suggested_capabilities` is advisory. Leave the required list empty when native Codex research is an allowed fallback. `warning_estimated_tokens` defaults to 50,000 and `maximum_estimated_tokens` to 100,000; the warning may be lowered for tighter contexts, but it cannot exceed the hard limit.

## Validate safely

Add an external profile directory to `AUDIO_ENGINE_INPUT_ROOTS` using the macOS/Linux `:` path separator, load the central environment, and run:

```bash
uv run python scripts/doctor.py --profile <absolute-or-repository-profile-path>
```

The loader uses `yaml.safe_load`, rejects executable YAML tags, refuses unsupported schema versions, and resolves symlinks before enforcing input-root containment. The doctor performs no network call or upload.

Use an IANA timezone such as `America/Los_Angeles`. Episode dates are derived from that timezone, not the host timezone. Publication environment references must be `PODCAST_FEED_TOKEN`, `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `PODCAST_BASE_URL`, and `R2_RETENTION_DAYS`; embedded values and alternate names fail validation so the profile cannot bypass typed central configuration.
