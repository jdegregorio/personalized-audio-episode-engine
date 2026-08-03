"""Publish one validated episode and conditionally update its private RSS feed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from audio_engine.audio import AudioAssemblyError
from audio_engine.config import EngineSettings
from audio_engine.lifecycle import LifecycleError
from audio_engine.publication import PublicationError, publish_episode
from audio_engine.rendering import TtsRenderingError
from audio_engine.scriptwriting import ScriptwritingError
from audio_engine.tts import TtsPreparationError


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
        result = publish_episode(
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
    except (
        AudioAssemblyError,
        LifecycleError,
        PublicationError,
        ScriptwritingError,
        TtsPreparationError,
        TtsRenderingError,
    ) as error:
        print(_error("publication_failed", str(error)), file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), separators=(",", ":"), sort_keys=True))
    return 2 if result.status == "deferred" else 0


if __name__ == "__main__":  # pragma: no cover - exercised through smoke tests
    raise SystemExit(main())
