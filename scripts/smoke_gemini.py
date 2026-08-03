"""Render one synthetic two-speaker Gemini sample for explicit live verification."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from audio_engine.artifacts import ArtifactReference, TtsHost, TtsSegmentPrompt
from audio_engine.gemini import GeminiSpeechRenderer
from audio_engine.rendering import TtsRenderingError, write_live_sample
from audio_engine.storage import atomic_write_json
from audio_engine.tts import (
    TTS_PROMPT_VERSION,
    SpeechRendererError,
    estimate_input_tokens,
    renderer_input,
)

_MODEL = "gemini-3.1-flash-tts-preview"
_TRANSCRIPT = "\n".join(
    (
        "Maya: Good morning. This is a synthetic audio check, built to test a calm "
        "two-host conversation without using current news or private information.",
        "Daniel: We are listening for stable voices, clear handoffs, comfortable pacing, "
        "and a clean distinction between the two speakers.",
        "Maya: The scene is intentionally simple: two colleagues in a quiet studio, "
        "explaining how a reliable system preserves completed work when one request needs "
        "to be tried again.",
        "Daniel: That means a later retry should focus only on the missing segment. Earlier "
        "audio stays exactly where it is, with its original checksum and completion time.",
        "Maya: We also keep production direction outside the spoken transcript. If this "
        "sample begins by reading labels, voice identifiers, or setup notes, the smoke check "
        "should be treated as unsuccessful.",
        "Daniel: The expected result is ordinary conversation, not a dramatic performance. "
        "I should sound grounded and analytical, while Maya remains warm, incisive, and "
        "concise.",
        "Maya: This final exchange gives the sample enough length to reveal obvious drift in "
        "pacing or voice identity.",
        "Daniel: And it closes with a direct confirmation that both configured speakers "
        "completed the synthetic Gemini text-to-speech check.",
        "",
    )
)


def build_live_prompt(female_voice: str, male_voice: str) -> TtsSegmentPrompt:
    prompt = TtsSegmentPrompt(
        contract_version="1.0",
        prompt_version=TTS_PROMPT_VERSION,
        provider="gemini",
        model=_MODEL,
        episode_script=ArtifactReference(
            artifact_type="script",
            path="live-smoke-script.json",
            sha256="sha256:" + "0" * 64,
        ),
        segment_id="tts_live_smoke",
        position=1,
        segment_count=1,
        scene_description=(
            "A calm public-radio-style conversation in a quiet studio at a conversational pace."
        ),
        director_notes=[
            "Speak only the exact transcript; never read production metadata aloud.",
            "Keep both recurring hosts natural, grounded, and distinct.",
        ],
        hosts=[
            TtsHost(
                name="Maya",
                voice=female_voice,
                description="calm, incisive, warm, concise",
            ),
            TtsHost(
                name="Daniel",
                voice=male_voice,
                description="curious, analytical, grounded, concise",
            ),
        ],
        continuity_context=None,
        transcript=_TRANSCRIPT,
        turn_ids=["turn_live_smoke"],
        estimated_input_tokens=1,
    )
    return prompt.model_copy(
        update={"estimated_input_tokens": estimate_input_tokens(renderer_input(prompt))}
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--female-voice", default="Kore")
    parser.add_argument("--male-voice", default="Charon")
    args = parser.parse_args(argv)
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print('{"code":"missing_gemini_api_key","result":"failed"}', file=sys.stderr)
        return 1
    try:
        args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        prompt = build_live_prompt(args.female_voice, args.male_voice)
        response = GeminiSpeechRenderer(api_key=key, model=_MODEL).render(prompt)
        rendered = write_live_sample(
            args.output,
            response,
            expected_duration_seconds=75,
        )
        metadata_path = args.output.with_suffix(".json")
        atomic_write_json(
            metadata_path,
            {
                "audio": args.output.name,
                "channels": rendered.channels,
                "duration_seconds": round(rendered.duration_seconds, 3),
                "female_voice": args.female_voice,
                "male_voice": args.male_voice,
                "provider_media_type": rendered.provider_media_type,
                "sample_rate_hz": rendered.sample_rate_hz,
                "status": "passed",
            },
        )
    except (OSError, SpeechRendererError, TtsRenderingError) as error:
        print(
            json.dumps(
                {"code": "gemini_live_smoke_failed", "message": str(error), "result": "failed"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "audio": str(args.output),
                "duration_seconds": round(rendered.duration_seconds, 3),
                "metadata": str(metadata_path),
                "result": "passed",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by explicit live smoke
    raise SystemExit(main())
