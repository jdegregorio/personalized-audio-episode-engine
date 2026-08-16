# Episode-profile authoring

Episode profiles are topic-specific YAML data validated before any run output is created. The engine understands generic sections and limits; it does not contain world, U.S., Seattle, news, sports, publisher, or taxonomy rules.

## Start from the example

Copy [`world-us-seattle-news.yaml`](../examples/profiles/world-us-seattle-news.yaml) to an allowed input root and change the data. Keep `schema_version: "1.0"` quoted. The authoritative machine-readable contract is [`episode-profile-v1.0.schema.json`](../schemas/episode-profile-v1.0.schema.json).

The main groups are:

- `identity` for feed identity and a title template containing `{date}`.
- `episode` and `audience` for the topic, arbitrary section IDs, exclusions, timezone, locale, and preferences.
- `collection` for source types, suggested or explicitly required capabilities, time window, generic candidate targets, and dossier warning/hard token limits.
- `editorial` for duration/item bounds, section targets, allowed-empty sections, profile-defined exclusion reason codes, and topic-specific policy data.
- `hosts`, `performance`, and `tts` for the two recurring speakers, conversation mode, and provider-neutral preparation limits.
- `publishing` for either `cloudflare_r2` feed metadata/environment references or a `local_private` output boundary. Never put an endpoint, bucket, public URL, token, retention value, or credential directly in a profile.

Every key is validated and unknown keys fail closed. Section IDs may be any lowercase identifier, but all candidate targets, editorial targets, and allowed-empty references must name a declared section. The two host names must be distinct. `editorial.exclusion_reason_codes` is an optional unique list; when populated, every plan exclusion must use one of those profile-owned identifiers. Keep codes topic-appropriate rather than adding engine taxonomy. `required_capabilities` is a hard preflight requirement; `suggested_capabilities` is advisory. Leave the required list empty when native Codex research is an allowed fallback. `warning_estimated_tokens` defaults to 50,000 and `maximum_estimated_tokens` to 100,000; the warning may be lowered for tighter contexts, but it cannot exceed the hard limit.

`performance.conversation_mode` is `standard` by default. Set it to `inquiry_driven` when the non-lead host should act as a listener proxy, ask a grounded next-level question within every planned segment, and avoid rigid announcer handoffs. See [`voice-and-conversation-design.md`](voice-and-conversation-design.md).

`performance.fatal_warning_codes` is an optional unique list that promotes selected script-quality warnings to validation errors. Supported codes are `excessive_performance_tags`, `excessive_reaction_turns`, `host_word_share`, `consecutive_host_turns`, `repeated_stock_phrase`, `missing_segment_takeaway`, `script_duration_preferred`, `missing_followup_question`, `abrupt_transition`, and `mechanical_turn_taking`. Leave it empty when warnings should remain visible without rejecting otherwise grounded prose. The fixed general thresholds are more than 70 percent of words for one host, more than three consecutive turns, reaction turns above the greater of two or one-fifth of all turns, and—when tags are `sparingly`—performance cues above the greater of one or one-quarter of all turns. Inquiry-driven scripts of at least eight turns warn when more than 90 percent of adjacent turns switch speakers.

The `tts` block selects the provider/model capability record and preparation limits. The Gemini model has an 8,192-token absolute input limit; keep `safe_input_tokens` at the default 7,000 so the complete provider prompt retains headroom. `target_segment_minutes` guides natural packing (the default is three); it never permits a prompt above the safe limit or a silent mid-turn text split. `maximum_retries` is zero through three and means retries after the initial request; three uses delays near 2, 5, and 12 seconds. Host `voice` values must be documented Gemini prebuilt IDs from the appropriate provider gender category, and the female and male voices must be distinct. The production profiles select the female/upbeat `Laomedeia` for Maya and the male/friendly `Achird` for Daniel; voice choice remains profile data while provider category validation prevents accidental convergence caused by an inverted assignment.

Use `publishing.provider: cloudflare_r2` only for material safe for the public-by-secret-link feed and include its fixed environment references. Use `publishing.provider: local_private` for Calendar, email, notes, or other sensitive material; its publishing block contains only `feed_title`, `language`, and the provider. Local-private finalization retains the valid MP3 in the private run workspace and refuses R2 publication. See [`personal-daily-briefing.md`](personal-daily-briefing.md).

## Validate safely

Add an external profile directory to `AUDIO_ENGINE_INPUT_ROOTS` using the macOS/Linux `:` path separator, load the central environment, and run:

```bash
uv run python scripts/doctor.py --profile <absolute-or-repository-profile-path>
```

The loader uses `yaml.safe_load`, rejects executable YAML tags, refuses unsupported schema versions, and resolves symlinks before enforcing input-root containment. The doctor performs no network call or upload.

After validation, start or resume only through the owning initializer:

```bash
uv run python scripts/init_run.py --profile <absolute-or-repository-profile-path>
```

The canonical key combines this profile ID with its timezone-derived local date. An unchanged compatible profile can resume the same failed/crash-interrupted workspace; changing the profile file/hash makes prior work incompatible and starts a new owning workspace. Within an active run, accepted profile, dossier, plan, or script hash changes invalidate only their dependent outputs. Do not edit a profile merely to force resume, bypass a validation limit, or repurpose an already published same-day episode.

Use an IANA timezone such as `America/Los_Angeles`. Episode dates are derived from that timezone, not the host timezone. For `cloudflare_r2`, publication environment references must be `PODCAST_FEED_TOKEN`, `R2_ENDPOINT_URL`, `R2_BUCKET_NAME`, `PODCAST_BASE_URL`, and `R2_RETENTION_DAYS`; embedded values and alternate names fail validation so the profile cannot bypass typed central configuration. A `local_private` publishing block has no publication environment references.
