"""Render missing prepared TTS segments with Gemini and preserve resumable state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from audio_engine.config import EngineSettings
from audio_engine.gemini import GeminiSpeechRenderer
from audio_engine.lifecycle import LifecycleError
from audio_engine.rendering import TtsRenderingError, open_render_run, render_missing_segments
from audio_engine.scriptwriting import ScriptwritingError
from audio_engine.tts import SpeechRendererError, TtsPreparationError


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
        context = open_render_run(
            args.run_directory,
            settings=settings,
            repo_root=Path(__file__).resolve().parents[1],
        )
        api_key = settings.gemini_api_key.get_secret_value()
        renderer = GeminiSpeechRenderer(api_key=api_key, model=context.manifest.model)
        result = render_missing_segments(context, renderer, sensitive_values=(api_key,))
    except ValidationError:
        print(
            _error("invalid_settings", "required environment configuration is invalid"),
            file=sys.stderr,
        )
        return 1
    except (
        LifecycleError,
        ScriptwritingError,
        SpeechRendererError,
        TtsPreparationError,
        TtsRenderingError,
    ) as error:
        print(_error("tts_rendering_failed", str(error)), file=sys.stderr)
        return 1

    print(json.dumps(result.to_dict(), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through smoke tests
    raise SystemExit(main())
