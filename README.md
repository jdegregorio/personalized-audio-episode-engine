# Personalized Audio Episode Engine

This repository will contain a profile-driven workflow that turns source-grounded research into a two-host audio episode and publishes it to a private-by-secret-link podcast feed. The approved MVP is intentionally one vertical slice: Codex supplies editorial judgment, while small Python scripts provide deterministic validation, state, audio, and publication operations.

Implementation follows the ordered pull requests in [`plan.md`](plan.md). The current delivery status is recorded in [`docs/implementation-status.md`](docs/implementation-status.md).

## Development setup

The supported development runtime is Python 3.12 on macOS or Ubuntu, managed by `uv`.

```bash
uv sync --locked --all-extras --dev
uv lock --check
uv build
artifact_venv="$(mktemp -d)/venv"
uv venv --python 3.12 "${artifact_venv}"
uv pip install --python "${artifact_venv}/bin/python" dist/*.whl
"${artifact_venv}/bin/python" -c "import audio_engine; print(audio_engine.__version__)"
```

Run the complete local gate:

```bash
uv run python scripts/check_repository.py
uv run python scripts/check_artifacts.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m "not live and not smoke" --cov=audio_engine --cov=scripts --cov-report=term-missing --cov-fail-under=85
uv run pytest -m "smoke and not live"
```

See [`docs/setup.md`](docs/setup.md) for workstation, account, and secret setup. Contributors must follow [`CONTRIBUTORS.md`](CONTRIBUTORS.md), including its worktree, review, evidence, and merge gates.

Validate the prepared host without contacting Gemini or R2:

```bash
uv run python scripts/doctor.py --profile examples/profiles/world-us-seattle-news.yaml
```

Episode profiles are strict, versioned YAML data. See [`docs/profile-authoring.md`](docs/profile-authoring.md) and the committed [`schemas/episode-profile-v1.0.schema.json`](schemas/episode-profile-v1.0.schema.json).

For offline collection verification, [`examples/profiles/synthetic-marine-brief.yaml`](examples/profiles/synthetic-marine-brief.yaml) is grounded in the committed synthetic corpus under `tests/fixtures/sources/marine-brief/`; it is test data, not a production feed.

Validate a persisted pipeline artifact without modifying it:

```bash
uv run python scripts/validate_artifact.py --type evidence --input tests/fixtures/artifacts/valid/evidence-dossier.json
```

The supported artifact types, versioning policy, evidence lineage, safe locators, and optional full-report output are documented in [`docs/artifact-contracts.md`](docs/artifact-contracts.md).

After loading the owner-managed environment, initialize one owner-checked local run:

```bash
uv run python scripts/init_run.py \
  --profile examples/profiles/world-us-seattle-news.yaml
```

The run layout, lifecycle stages, invalidation, same-episode no-op behavior, and stale-lease recovery are documented in [`docs/run-lifecycle.md`](docs/run-lifecycle.md).

## Collection workflow

The repository skill at [`.agents/skills/produce-audio-episode/SKILL.md`](.agents/skills/produce-audio-episode/SKILL.md) routes one profile through the durable workflow. During collection it inspects capabilities already available to Codex, uses a suitable specialized capability when helpful, and otherwise uses native public-web research when the profile permits it. Specialized collectors are optional and are never installed by a production run; see [`docs/optional-collectors.md`](docs/optional-collectors.md).

After initialization, record the chosen method and validate the dossier through the same deterministic boundary regardless of research method:

```bash
uv run python scripts/select_collection_method.py --run <run-directory>
uv run python scripts/record_collection.py --run <run-directory>
```

The first invalid dossier receives one machine-readable repair opportunity; a second invalid attempt fails the run. Collection recovery is documented in [`docs/troubleshooting.md`](docs/troubleshooting.md).

## Editorial planning workflow

After valid collection, start the distinct editorial phase described by the skill's [`editorial-planning.md`](.agents/skills/produce-audio-episode/references/editorial-planning.md) reference. Read the complete profile and dossier, write one structured plan, then record it:

```bash
uv run python scripts/record_editorial_plan.py --run <run-directory>
```

The recorder binds the current profile/dossier hashes and editorial prompt version, checks every candidate disposition plus profile-defined sections, hosts, reason codes, item/duration bounds, and disagreement notes, and allows one recorded repair. A valid plan advances to the separate script phase; it does not contain dialogue or invoke another model.

## Scriptwriting workflow

In a separate Codex phase, follow the skill's [`scriptwriting.md`](.agents/skills/produce-audio-episode/references/scriptwriting.md) reference. Read the complete profile, dossier, and plan, write the structured two-host script, then record it:

```bash
uv run python scripts/record_script.py --run <run-directory>
```

The recorder binds current input hashes and script prompt version, checks claim and source lineage, required attribution and qualifications, disagreement, speaker/voice configuration, spoken-text safety, duration, conversational-quality warnings, and TTS input limits. It allows one recorded repair and deterministically writes `transcript.txt` from the accepted turns, so the spoken projection cannot diverge from the auditable script. A valid script advances to `tts`; it does not call Gemini.

## TTS preparation workflow

At `tts`, follow the skill's [`tts-preparation.md`](.agents/skills/produce-audio-episode/references/tts-preparation.md) reference and prepare the accepted script:

```bash
uv run python scripts/prepare_tts.py --run <run-directory>
```

The preparer revalidates the script/transcript, applies the configured model capability limits, prefers natural two-to-four-minute boundaries, and writes `tts/manifest.json` plus ordered atomic segment prompt files. Each provider input begins with an explicit synthesis instruction and delimits the exact spoken transcript from non-spoken direction. An unchanged rerun verifies hashes and returns `already_prepared` without rewriting valid outputs.

## Gemini rendering workflow

After preparation, follow the skill's [`tts-rendering.md`](.agents/skills/produce-audio-episode/references/tts-rendering.md) reference and render only missing segments:

```bash
uv run python scripts/render_audio.py --run <run-directory>
```

The renderer makes bounded Gemini calls with exactly two configured voices and project-owned retries near 2, 5, and 12 seconds. It preserves raw 24 kHz PCM before packaging each decodable WAV, then records that segment immediately. Exhaustion leaves the run at `tts` with completed segments intact and segment-specific resume guidance; completion advances to `audio`. An unchanged rerun validates hashes and audio before returning `already_rendered` without contacting Gemini.

## Final audio assembly

At `audio`, follow the skill's [`audio-assembly.md`](.agents/skills/produce-audio-episode/references/audio-assembly.md) reference and assemble the rendered segments:

```bash
uv run python scripts/assemble_audio.py --run <run-directory>
```

The command revalidates each ordered PCM WAV, uses bounded FFmpeg/FFprobe processes to concatenate and encode a 48 kHz mono MP3, performs a full decode check, and atomically promotes `episode.mp3` only after codec, media type, duration, sample rate, channels, and size pass. Success advances to `publication`; a failed conversion leaves all rendered segments reusable at `audio` with recovery guidance. An unchanged rerun revalidates the recorded MP3 and returns `already_assembled` without rewriting it.

## Security boundary

The MVP feed contains public-news content but uses an unguessable URL. That URL is access material, not authentication. Never commit or paste credentials, tokenized object keys, runtime data, or complete feed URLs. Profiles containing personal or otherwise sensitive information are outside the MVP and require a separate authenticated or encrypted publication design.
