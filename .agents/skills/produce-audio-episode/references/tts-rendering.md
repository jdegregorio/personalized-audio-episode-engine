# TTS rendering

Run this stage only when `state.json.tts_preparation` and its manifest/prompts are valid. Do not edit script, transcript, prompts, voice IDs, state, or completed audio.

```bash
uv run python scripts/render_audio.py --run <run-directory>
```

The command revalidates every preparation input and completed segment before contacting Gemini. It will render only missing segments, in manifest order, with the two profile voices; it makes bounded calls, retries a failed segment up to three times, preserves raw PCM before WAV packaging, and records every validated success immediately.

## Inspect the result

- `rendered`: reload state, require `current_stage: audio` and `tts_rendering.status: complete`, then inspect every recorded raw/WAV reference and duration.
- `already_rendered`: all preparation, raw/WAV hashes, and WAV parameters revalidated without a provider call.
- `failed`: read `tts_rendering.failed_segment_id` and its redacted recovery guidance. Correct the provider/configuration issue and rerun the same command; never remove completed segments.

Only `scripts/render_audio.py` may advance the run from `tts` to `audio`. Do not concatenate, encode, publish, or make subjective automated quality decisions in this stage. Generated audio is private runtime data and must never be committed or pasted into PR evidence.
