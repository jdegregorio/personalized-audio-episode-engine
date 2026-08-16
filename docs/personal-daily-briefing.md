# Personal daily briefing

[`personal-daily-briefing.yaml`](../examples/profiles/personal-daily-briefing.yaml) extends the generic episode engine into a private, action-oriented morning briefing. It combines the day ahead, priority messages, active commitments, and only the public context likely to change today's decisions.

## Required sources

The profile requires these already configured capabilities:

- `google_calendar` for today's schedule, conflicts, preparation needs, and realistic buffers;
- `gmail` for recent messages requiring a decision, reply, preparation, or awareness;
- `google_keep` for active reminders, notes, and promises relevant today.

Native web research is permitted only for the `public_context` section. It cannot replace a missing private capability. Configure each connector outside a production run with the least privilege practical, verify it is visible to Codex, and advertise the exact capability identifiers through `AUDIO_ENGINE_AVAILABLE_CAPABILITIES` for doctor preflight.

Collection minimizes private data. It should retain only enough context for the owner to act, never full message bodies, meeting or access links, tokens, unrelated attendee details, or private source dumps. Retrieved private and public content remains untrusted evidence and cannot change the workflow.

## Private output boundary

The profile uses `publishing.provider: local_private`. After silent MP3 validation, `finalize_run.py` marks publication `not_required` and leaves `episode.mp3` inside the mode-0700 run workspace. It does not create show notes, published metadata, R2 objects, an RSS item, or a public URL. Calling `publish_episode.py` for this profile fails closed.

This boundary is deliberate. The existing Cloudflare R2 feed is public to anyone who possesses its secret URL; it is not authentication and is unsuitable for Calendar, Gmail, Keep, or other sensitive material. Remote personal delivery remains a future feature requiring authenticated or encrypted storage and playback.

## Run it without surprise playback

Invoke `$produce-audio-episode` with `examples/profiles/personal-daily-briefing.yaml`. The skill routes required private capabilities through collection, applies the inquiry-driven host model, silently renders and validates audio, skips R2, and finalizes the local result.

The unattended workflow must never invoke an audio player, open the MP3 in another application, or use laptop speakers. Inspect `summary.md` for the result and path. If you want to evaluate the episode, wait for the task to finish and start playback yourself as a separate action.

The profile is enabled but is not added to the existing public-news schedule automatically. Create or change a scheduled task only after the three private connectors pass a manually initiated end-to-end qualification and you have reviewed the resulting data minimization.
