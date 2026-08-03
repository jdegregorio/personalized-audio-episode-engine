"""Finalize one run as completed or failed and release its episode lease."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from audio_engine.config import EngineSettings
from audio_engine.lifecycle import LifecycleError, finalize_run


def _error(code: str, message: str) -> str:
    return json.dumps(
        {"code": code, "message": message, "status": "failed"},
        separators=(",", ":"),
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path, dest="run_directory")
    args = parser.parse_args(argv)
    try:
        settings = EngineSettings.from_environment()
        result = finalize_run(
            args.run_directory,
            settings=settings,
            repo_root=Path(__file__).resolve().parents[1],
        )
    except ValidationError:
        print(
            _error("invalid_settings", "required environment configuration is invalid"),
            file=sys.stderr,
        )
        return 1
    except LifecycleError as error:
        print(_error("finalization_failed", str(error)), file=sys.stderr)
        return 1

    output = json.dumps(result.to_dict(), separators=(",", ":"), sort_keys=True)
    if result.status == "failed":
        print(output, file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through smoke tests
    raise SystemExit(main())
