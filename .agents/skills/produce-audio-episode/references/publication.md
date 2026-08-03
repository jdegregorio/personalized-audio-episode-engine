# Publication

Enter this phase only when `state.json.current_stage` is `publication` and `final_audio_validation.status` is `valid`. Load the central environment, then run:

```bash
uv run python scripts/publish_episode.py --run <run-directory>
```

The command revalidates the accepted profile, dossier, plan, script, transcript, every rendered segment, and final MP3. It deterministically creates escaped HTML show notes and published episode metadata, uploads audio/transcript/notes/metadata below the tokenized episode prefix, and requires both S3 HEAD and public-body verification for each asset. Only then does it acquire the feed lock, re-read the latest RSS and ETag, prune expiry-bound entries, upsert the stable `<feed-id>:<profile-id>:<date>` GUID, validate RSS 2.0, and conditionally write the feed last with `If-Match` for replacement or `If-None-Match: *` for creation. It also reads the winning feed revision through S3 and the public endpoint before recording success.

Interpret results as follows:

- `published`: all four assets and the complete conditional feed revision succeeded; state records only redacted locations.
- `already_published`: a rerun revalidated and safely upserted the same GUID without duplication.
- `deferred`: the bounded feed lock or ETag retry did not converge. Valid audio and uploaded-but-undiscoverable assets remain safe; rerun only this command. The CLI exits `2` for this result.
- `publication_failed`: correct the named configuration, public-read, asset, or feed problem and rerun this command. Do not rerender or reassemble valid audio.

Never print, inspect, or paste the feed token, tokenized object keys, complete public feed URL, R2 credentials, or provider error bodies. Do not create buckets, domains, tokens, or lifecycle rules from the runtime. `episode.json` omits only its mathematically self-referential own content hash; the uploaded object is still verified by its actual SHA-256 and the local metadata artifact is hash-bound in state.
