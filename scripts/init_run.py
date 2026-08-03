"""Acquire episode ownership and initialize one durable run workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from audio_engine.config import EngineSettings
from audio_engine.lifecycle import LifecycleError, initialize_run


def _error_payload(code: str, message: str, *, fields: list[str] | None = None) -> str:
    payload: dict[str, object] = {"code": code, "message": message, "result": "failed"}
    if fields:
        payload["fields"] = fields
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--codex-model", help="selected Codex model when observable")
    args = parser.parse_args(argv)

    try:
        settings = EngineSettings.from_environment()
    except ValidationError as error:
        fields = sorted({str(item["loc"][0]) for item in error.errors() if item["loc"]})
        print(
            _error_payload(
                "invalid_settings",
                "required environment configuration is missing or invalid",
                fields=fields,
            ),
            file=sys.stderr,
        )
        return 1

    try:
        result = initialize_run(
            args.profile,
            settings=settings,
            repo_root=Path(__file__).resolve().parents[1],
            codex_model=args.codex_model,
        )
    except LifecycleError as error:
        print(_error_payload("initialization_failed", str(error)), file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by smoke tests
    raise SystemExit(main())
