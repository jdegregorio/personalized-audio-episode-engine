"""Select and record a capability-neutral collection method for one active run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from audio_engine.artifacts import RunFailure
from audio_engine.collection import (
    COLLECTION_PROMPT_VERSION,
    CollectionError,
    load_collection_request,
    open_collection_run,
    select_collection_method,
)
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import (
    LifecycleError,
    load_run_state,
    mark_run_failed,
    record_collection_method,
)


def _capabilities(values: list[str], parser: argparse.ArgumentParser) -> dict[str, str | None]:
    capabilities: dict[str, str | None] = {}
    for value in values:
        name, separator, version = value.partition("=")
        if not name or (separator and not version) or name in capabilities:
            parser.error("--capability must be a unique NAME or NAME=VERSION")
        capabilities[name] = version if separator else None
    return capabilities


def _print_error(code: str, message: str) -> None:
    print(
        json.dumps(
            {"code": code, "message": message, "result": "failed"},
            separators=(",", ":"),
            sort_keys=True,
        ),
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, dest="run_directory")
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="suitable available NAME or NAME=VERSION; repeat as needed",
    )
    parser.add_argument("--preferred-capability")
    parser.add_argument("--failed-capability", action="append", default=[])
    args = parser.parse_args(argv)
    available = _capabilities(args.capability, parser)

    try:
        settings = EngineSettings.from_environment()
        context = open_collection_run(
            args.run_directory,
            settings=settings,
            repo_root=Path(__file__).resolve().parents[1],
        )
        state = load_run_state(context.workspace.state_path)
        request = load_collection_request(
            context.workspace,
            state.artifacts.get("collection_request"),
        )
    except ValidationError:
        _print_error("invalid_settings", "required environment configuration is invalid")
        return 1
    except CollectionError as error:
        _print_error("collection_selection_failed", str(error))
        return 1
    except LifecycleError as error:
        _print_error("collection_selection_failed", str(error))
        return 1

    try:
        method = select_collection_method(
            request,
            available,
            preferred_capability=args.preferred_capability,
            failed_capabilities=[
                *state.failed_collection_capabilities,
                *args.failed_capability,
            ],
        )
    except CollectionError as error:
        try:
            mark_run_failed(
                context.workspace,
                context.manager,
                context.run_id,
                failure=RunFailure(
                    stage="collection",
                    code="collection_capability_unavailable",
                    message=str(error),
                    recovery_guidance=(
                        "Install or configure the required capability, or update the profile to "
                        "allow native public-web research, then start a new owning run."
                    ),
                ),
                now=datetime.now(UTC),
            )
        except LifecycleError:
            _print_error("collection_selection_failed", str(error))
            return 1
        _print_error("collection_capability_unavailable", str(error))
        return 1

    try:
        record_collection_method(
            context.workspace,
            context.manager,
            context.run_id,
            method=method,
            prompt_version=COLLECTION_PROMPT_VERSION,
            failed_capabilities=args.failed_capability,
        )
    except LifecycleError as error:
        _print_error("collection_selection_failed", str(error))
        return 1

    print(
        json.dumps(
            {
                "collection_method": method.model_dump(mode="json"),
                "failed_capabilities": list(
                    dict.fromkeys([*state.failed_collection_capabilities, *args.failed_capability])
                ),
                "result": "selected",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through smoke tests
    raise SystemExit(main())
