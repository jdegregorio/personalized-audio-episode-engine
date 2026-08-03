# Operations

The engine supports validated environment/profile preflight, deterministic artifact/lineage validation, owner-checked run initialization, and capability-neutral evidence collection. Editorial planning, rendering, and publication arrive only in their owning PRs in [`plan.md`](../plan.md).

## Development gate

Run from the active feature worktree:

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

The `not live and not smoke` suite is deterministic and must not read the owner's real environment file or access a network service. Smoke tests prove user-visible behavior at the smallest useful boundary. Live tests remain explicit and use the narrow `live-smoke` environment only after their implementation PR.

## Environment preflight

Load the owner-managed environment as described in [`setup.md`](setup.md), then run:

```bash
uv run python scripts/doctor.py --profile examples/profiles/world-us-seattle-news.yaml
```

`PASS` means local configuration and tools are structurally ready; it is not a live Gemini or R2 probe. A `FAIL` line names the setting, tool, root, profile, or required capability the operator must fix without echoing its value.

## Artifact validation

Validate one JSON artifact through the public contract boundary:

```bash
uv run python scripts/validate_artifact.py --type evidence --input <artifact-path>
```

Fatal validation writes a concise JSON result to stderr and exits non-zero. Pass `--report <report-path>` to persist the complete validation result for a repair; the report path may not overwrite the input. Filesystem source locators require one or more explicit `--allowed-input-root <path>` arguments. See [`artifact-contracts.md`](artifact-contracts.md) for supported types and the boundary between structural validation and later phase policy.

## Run initialization

After loading the central environment, acquire ownership and create the collection request, state, and summary:

```bash
uv run python scripts/init_run.py \
  --profile examples/profiles/world-us-seattle-news.yaml
```

The command returns compact JSON for either an initialized owner or a successful same-episode no-op. See [`run-lifecycle.md`](run-lifecycle.md) for the layout, state transitions, invalidation rules, concurrency UAT, stale recovery, and rollback procedure.

## Evidence collection

Follow the production [skill](../.agents/skills/produce-audio-episode/SKILL.md). After inspecting available capabilities, record either an already available suitable capability or native public-web fallback:

```bash
uv run python scripts/select_collection_method.py --run <run-directory>
```

The agent writes one dossier to the generated request's `output_path`, then records it:

```bash
uv run python scripts/record_collection.py --run <run-directory>
```

The recorder binds current request lineage, selected method, prompt version, and configured limits; validates and persists the dossier; writes a hashed validation report; and advances only valid evidence. It returns `repair_required` once, fails/releases after a second invalid attempt, and returns `already_valid` when resuming verified collection. See [`optional-collectors.md`](optional-collectors.md) and [`troubleshooting.md`](troubleshooting.md).

## Production invariants

- One independent Codex run processes one profile.
- Files are the system of record; a stage advances only after durable validation.
- Use only documented repository commands. A production run never writes ad hoc source code.
- Production runs do not modify tracked code, dependencies, schemas, profiles, or documentation.
- Resume valid work rather than rerunning successful external operations.
- Never log credentials, tokenized object keys, or complete feed URLs.
- Default CI cannot synthesize speech or publish objects because it receives no production secrets.

## Rollback at this phase

No current command contacts Gemini or R2. Initialization and collection create only local runtime files after acquiring an episode lease; Codex research itself may access public sources or an already configured capability. Follow the lease-aware rollback in [`run-lifecycle.md`](run-lifecycle.md); do not manually remove a live lock. Invalid generated artifacts are repaired at their owning stage rather than bypassing version, lineage, locator, or evidence validation.

Service-specific recovery and rotation are documented in [`cloudflare-r2.md`](cloudflare-r2.md) and will be expanded alongside their implementations.
