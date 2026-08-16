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
    validate_gemini_voice_pair,
)

_MODEL = "gemini-3.1-flash-tts-preview"
_TRANSCRIPT = "\n".join(
    (
        "Maya: Okay, tiny morning mystery. Our completely fictional office put a bowl of "
        "tangerines beside the coffee machine, and somehow the tangerines vanished before "
        "the coffee did.",
        "Daniel: Before the coffee? That's either a wellness breakthrough or somebody hid "
        "the good beans. What did our very serious imaginary investigation find?",
        "Maya: Mostly that people will eat fruit when it is directly in the path of caffeine. "
        "Move the bowl six feet away and suddenly a tangerine requires project planning.",
        "Maya: Which, honestly, feels unfair to the tangerine. It already came in its own "
        "little jacket.",
        "Daniel: Strong packaging. Terrible marketing department. But is the useful idea "
        "really just that convenience beats good intentions?",
        "Maya: Pretty much. Tiny bits of friction matter. If the healthy choice is visible and "
        "easy, people don't have to stage a personal summit before breakfast.",
        "Daniel: So what would you change next in this deeply rigorous fictional workplace?",
        "Maya: Put water beside the tangerines, keep the coffee where it is, and absolutely do "
        "not form a produce committee. That's how the bananas start requesting meetings.",
        "Daniel: Sensible. We've learned something useful, nobody had to sound like an "
        "announcer, and the imaginary bananas remain off the calendar.",
        "",
    )
)


def build_live_prompt(female_voice: str, male_voice: str) -> TtsSegmentPrompt:
    validate_gemini_voice_pair(female_voice, male_voice)
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
            "A bright, relaxed morning conversation between two quick, friendly colleagues. "
            "They are smiling, reacting to each other, and having genuine fun with a small idea."
        ),
        director_notes=[
            "Speak only the exact transcript; never read production metadata aloud.",
            "Preserve each host's exact register, timbre, cadence, energy, and personality.",
            "This is lively natural banter, not news reading: vary pace, use contractions, let "
            "reactions breathe, and keep an audible smile.",
            "Keep Maya bright, quick, and playfully spunky; keep Daniel lower, friendly, loose, "
            "and lightly wry. Never blend them.",
            "Respond to the humor and meaning of the prior line instead of resetting each turn.",
        ],
        hosts=[
            TtsHost(
                name="Maya",
                voice=female_voice,
                description=(
                    "Adult woman with a bright, lightly higher register, crisp articulation, "
                    "an audible smile, quick playful wit, and lively spunky curiosity."
                ),
            ),
            TtsHost(
                name="Daniel",
                voice=male_voice,
                description=(
                    "Adult man with a friendly lower register, loose conversational cadence, "
                    "easy curiosity, responsive amusement, and light dry wit."
                ),
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
    parser.add_argument("--female-voice", default="Laomedeia")
    parser.add_argument("--male-voice", default="Achird")
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
