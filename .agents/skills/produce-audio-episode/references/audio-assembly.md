# Final audio assembly

Run this deterministic stage only at `audio` after `tts_rendering.status` is `complete`. Do not edit segment files, reorder the manifest, add music/effects/mastering, modify voices, or publish an unvalidated file.

```bash
uv run python scripts/assemble_audio.py --run <run-directory>
```

The command revalidates every manifest-ordered WAV and its recorded hash, probes and fully decodes each input, and uses bounded FFmpeg to concatenate and encode a mono 48 kHz MP3. It applies only technical format conversion—no creative processing. The temporary output must pass codec/container, `audio/mpeg`, summed-duration tolerance, sample-rate, channel, byte-size, hash, and full-decode checks before atomic promotion to `episode.mp3` and advancement to `publication`.

## Inspect the result

- `assembled`: reload `state.json`; require `current_stage: publication`, `final_audio_validation.status: valid`, and exact equality between `final_audio_validation.artifact` and `artifacts.final_audio`. Play `episode.mp3` end to end.
- `already_assembled`: the recorded MP3 hash and all technical validation fields revalidated without rewriting the file.
- `failed`: read the final-audio message and summary, correct FFmpeg/FFprobe or the recorded segment issue, then rerun this command. Completed PCM/WAV segments remain reusable; do not call Gemini again.

Only `scripts/assemble_audio.py` may advance from `audio` to `publication`. Generated audio is private runtime data and must never be committed or pasted into PR evidence.
