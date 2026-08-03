# Development and service setup

This guide separates ordinary offline development from later live Gemini, Cloudflare R2, and scheduled-run qualification. Default tests are secret-free and must never contact a production service.

## Prerequisites

Install the following on macOS or Ubuntu:

- Git with access to the repository and GitHub CLI authentication.
- `uv` and a `uv`-managed Python 3.12 interpreter.
- FFmpeg and FFprobe.
- OpenSSL.
- The signed-in Codex desktop application for manual and scheduled production runs.
- AntennaPod on the playback device for PR 11 and PR 13 acceptance.

Verify the non-sensitive tools:

```bash
git --version
gh auth status
uv --version
uv python find 3.12
ffmpeg -version
ffprobe -version
codex --version
openssl version
```

The production host also needs stable outbound HTTPS/DNS, sufficient disk space, a stable primary checkout, and a power policy that keeps the machine and Codex app available during the schedule. No inbound port, VPN, local web server, database, or queue is required.

## Accounts and external resources

Before live qualification, the repository owner provides:

- A Gemini API key with billing, quota, region, and model access suitable for the selected TTS model.
- One dedicated Cloudflare R2 bucket and public endpoint configured by [`cloudflare-r2.md`](cloudflare-r2.md).
- An authenticated GitHub CLI session with permission to manage this repository's Actions environment.
- A Codex scheduler and AntennaPod device.

The application does not require an OpenAI API key for Codex editorial work, a Cloudflare global API key, or credentials for source-specific services.

## Central configuration

Feature worktrees must not contain private `.env` files. The owner-managed setup helper stores all values in:

```text
/Users/jdegregorio/.config/personalized-audio-episode-engine/secrets.env
```

The parent directory must have mode `0700` and the file mode `0600`. The prepared helper is:

```bash
/Users/jdegregorio/.config/personalized-audio-episode-engine/setup.zsh
```

It prompts without echo, preserves or creates the feed token, creates stable mode-`0700` runtime and staging directories below the owner data directory, records those absolute roots, and uploads provider values one way to the `live-smoke` GitHub environment when `gh` is authenticated. Pass `--local-only` to skip GitHub synchronization. GitHub is a delivery target, not a backup, because uploaded secret values cannot be retrieved.

Load values into a worktree shell without copying the file:

```bash
set -a
source /Users/jdegregorio/.config/personalized-audio-episode-engine/secrets.env
set +a
```

The required names are also documented with placeholders in [`.env.example`](../.env.example):

| Kind | Name | Owner and purpose |
| --- | --- | --- |
| Secret | `GEMINI_API_KEY` | Owner-managed Gemini TTS credential |
| Secret | `PODCAST_FEED_TOKEN` | At least 32 random bytes encoded as URL-safe text; grants knowledge of the feed URL |
| Secret | `R2_ACCESS_KEY_ID` | Bucket-scoped R2 runtime access-key ID |
| Secret | `R2_SECRET_ACCESS_KEY` | Bucket-scoped R2 runtime secret |
| Setting | `R2_ENDPOINT_URL` | Account-specific S3 endpoint, independent of the public origin |
| Setting | `R2_BUCKET_NAME` | Dedicated, non-sensitive bucket name |
| Setting | `PODCAST_BASE_URL` | Public HTTPS origin only; contains no feed token or object key |
| Setting | `R2_RETENTION_DAYS` | Positive integer matching the `episodes/` lifecycle rule |
| Path | `AUDIO_ENGINE_RUNTIME_ROOT` | Existing writable root for durable run state |
| Path | `AUDIO_ENGINE_STAGING_ROOT` | Existing writable root for temporary assembled output |
| Optional paths | `AUDIO_ENGINE_INPUT_ROOTS` | Additional absolute profile/input roots separated by `:` on macOS/Linux |
| Optional setting | `AUDIO_ENGINE_MAX_RUN_AGE_SECONDS` | Stale episode-lease threshold, 60–604,800 seconds; defaults to 21,600 |
| Optional setting | `AUDIO_ENGINE_AVAILABLE_CAPABILITIES` | Comma-separated identifiers for capabilities a profile explicitly requires |

Never print values while checking configuration. On the target zsh host, verify presence only:

```bash
for name in GEMINI_API_KEY PODCAST_FEED_TOKEN R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT_URL R2_BUCKET_NAME PODCAST_BASE_URL R2_RETENTION_DAYS AUDIO_ENGINE_RUNTIME_ROOT AUDIO_ENGINE_STAGING_ROOT; do
  test -n "${(P)name}" || { print -- "$name is missing"; exit 1; }
done
```

## Install and verify the repository

Each PR starts from the latest `origin/main` in a new sibling worktree as required by [`CONTRIBUTORS.md`](../CONTRIBUTORS.md). In that worktree:

```bash
uv sync --locked --all-extras --dev
uv lock --check
uv build
artifact_venv="$(mktemp -d)/venv"
uv venv --python 3.12 "${artifact_venv}"
uv pip install --python "${artifact_venv}/bin/python" dist/*.whl
"${artifact_venv}/bin/python" -c "import audio_engine; print(audio_engine.__version__)"
uv run python scripts/check_repository.py
uv run python scripts/check_artifacts.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m "not live and not smoke" --cov=audio_engine --cov=scripts --cov-report=term-missing --cov-fail-under=85
uv run pytest -m "smoke and not live"
```

After loading the external environment, run the non-networking preflight:

```bash
uv run python scripts/doctor.py --profile examples/profiles/world-us-seattle-news.yaml
```

The doctor checks tools, the lock, settings shape, writable roots, path-safe profile validity, publication environment references, and explicitly required capabilities. It prints only status and variable names; it does not print values, create run output, call Gemini, upload to R2, or prove live-service access. PR 09 adds a live Gemini smoke; PR 11 adds the R2 probe and publication UAT; PR 13 activates and qualifies the local schedule.

## Troubleshooting and rollback

- If `uv sync --locked` reports drift, do not regenerate the lock outside a dependency-owning PR.
- If Python 3.12 is missing, install it with `uv python install 3.12` and retry.
- If FFmpeg or FFprobe is absent, install the platform package before audio-owning PRs.
- If central configuration is missing, rerun the helper; never copy values into a worktree.
- If the doctor rejects a profile outside the repository examples, add its absolute parent to `AUDIO_ENGINE_INPUT_ROOTS`; do not weaken path checks or use a symlink escape.
- If a credential is exposed, revoke or rotate it immediately and remove it from all logs and evidence. Feed-token rotation also changes the secret feed URL and requires republishing.
- To disable live operation, remove or disable the scheduled task, revoke the bucket token, and disable R2 public access. Offline development remains usable.
