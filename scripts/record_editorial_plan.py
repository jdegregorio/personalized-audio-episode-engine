"""Validate and record one of at most two editorial-plan attempts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from audio_engine.config import EngineSettings
from audio_engine.editorial import EditorialError, open_editorial_run, record_editorial_attempt
from audio_engine.lifecycle import LifecycleError


def _error(code: str, message: str) -> str:
    return json.dumps(
        {"code": code, "message": message, "result": "failed"},
        separators=(",", ":"),
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, dest="run_directory")
    args = parser.parse_args(argv)

    try:
        settings = EngineSettings.from_environment()
        context = open_editorial_run(
            args.run_directory,
            settings=settings,
            repo_root=Path(__file__).resolve().parents[1],
        )
        result = record_editorial_attempt(
            context.workspace,
            context.manager,
            context.run_id,
            profile=context.profile,
            candidate_path=context.workspace.run_directory / "editorial-plan.json",
            allowed_input_roots=context.allowed_input_roots,
            allowed_profile_roots=context.allowed_profile_roots,
        )
    except ValidationError:
        print(
            _error("invalid_settings", "required environment configuration is invalid"),
            file=sys.stderr,
        )
        return 1
    except (EditorialError, LifecycleError) as error:
        print(_error("editorial_record_failed", str(error)), file=sys.stderr)
        return 1

    output = json.dumps(result.to_dict(), separators=(",", ":"), sort_keys=True)
    if result.status in {"accepted", "already_valid"}:
        print(output)
        return 0
    print(output, file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover - exercised through smoke tests
    raise SystemExit(main())
