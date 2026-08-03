# TTS preparation

Run this deterministic stage only after the structured script and transcript are accepted. Do not edit either input, call Gemini, select voices, or create audio during preparation.

```bash
uv run python scripts/prepare_tts.py --run <run-directory>
```

The command revalidates the complete script lineage and exact transcript before doing any work. It uses the configured provider/model capability record, rejects a safe limit above the model's absolute limit, and estimates the complete structured provider input—not transcript text alone.

## Inspect the result

- `prepared`: reload `state.json`, then inspect `tts/manifest.json` and every referenced `tts/segment-<NNN>.json`.
- `already_prepared`: every input, manifest, prompt, speaker, token estimate, and transcript projection was reverified without rewriting valid outputs.
- `failed`: stop and report the concise recovery message. Do not bypass the token limit or split a spoken turn manually in generated files.

Each prompt keeps scene direction, director notes, host descriptions/voices, segment position, and minimal prior context in separate fields from `transcript`. The transcript fields, in manifest order, must reproduce `transcript.txt` byte for byte. Host names and voices remain identical across prompts.

Natural script, planned-segment, section, transition, and closing-recap boundaries are preferred. Preparation targets two-to-four-minute requests and splits a discussion only when the configured safe token limit requires it. A single spoken turn that cannot fit fails closed so no prose is silently rewritten.

Preparation has no credential or network requirement beyond the repository's normal configured preflight. Rendering, retries, raw audio, and voice-pair selection begin in PR 09.
