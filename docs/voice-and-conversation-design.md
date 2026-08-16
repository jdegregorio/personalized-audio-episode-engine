# Voice and conversation design

The engine aims for an approachable public-radio conversation, not an imitation of any identifiable presenter, program, or network voice. The recurring hosts have original names and profiles; “public-radio” describes clarity, curiosity, warmth, pacing, and editorial discipline.

## Research basis

The implementation follows two provider facts and two observed editorial patterns:

- Google's [Gemini speech-generation guidance](https://ai.google.dev/gemini-api/docs/speech-generation) recommends natural-language control through an audio profile, scene, director's notes, sample context, and transcript. It describes `Laomedeia` as upbeat and `Achird` as friendly.
- Google's [Gemini TTS voice catalog](https://docs.cloud.google.com/text-to-speech/docs/gemini-tts) classifies `Laomedeia` as female and `Achird` as male. The engine validates those provider categories instead of relying on name or prompt wording alone.
- An official [Up First transcript](https://www.npr.org/transcripts/g-s1-72078) shows co-host questions moving from the basic event to authority, likelihood, implications, and what comes next. The question is a bridge into deeper reporting, not an ornamental handoff.
- Planet Money describes its intended feel as a knowledgeable friend explaining a complicated subject in an enjoyable conversation in its [show description](https://www.npr.org/sections/money/2011/04/27/135599807/about-planet-money). An official [Planet Money transcript](https://www.npr.org/transcripts/1228085818) illustrates short listener-proxy questions, reactions, callbacks, and explanatory answers with varied turn length.

These are design inferences from public examples, not a claim that every episode uses one formula.

## Stable recurring voices

Every TTS request repeats the same immutable Audio Profile for each host. The profile binds:

- the exact prebuilt voice ID;
- vocal register, timbre, cadence, energy, and articulation;
- the host's recurring conversational role and personality;
- explicit direction not to swap, average, reinterpret, or blend the hosts across segments.

The default profiles use Maya with `Laomedeia`: an adult woman with a bright, lightly higher register, audible smile, quick reactions, and playfully spunky wit. Daniel uses `Achird`: an adult man with a friendly lower register, loose cadence, responsive amusement, and light dry wit. Both should sound like smart friends thinking aloud, not anchors reading finished copy. The profiles ask for personality without caricature, exaggerated pitch, or invented personal experience.

TTS preparation rejects a female host configured with a documented male-category Gemini voice, a male host configured with a female-category voice, or any undocumented voice. Voice identity is profile data, but the provider catalog is a validated capability boundary.

## Inquiry-driven conversation

An `inquiry_driven` profile uses this flexible arc within each story or briefing item:

1. Establish the essential fact, commitment, or situation.
2. Let the other host ask the next question a thoughtful listener would ask.
3. Answer with how, why, consequence, uncertainty, evidence, tradeoff, or what to watch next.
4. Add a concise interpretation, practical implication, or bounded reaction.
5. Earn the handoff from the preceding takeaway, open question, consequence, or shared theme.

Turn length and speaker order follow the material. Perfect alternation, generic resets such as “moving on,” and questions that merely repeat the topic are discouraged. Light wit is welcome when it emerges from low-stakes material; it must not trivialize harm or weaken factual precision.

The script validator reports three inquiry-specific signals:

- `missing_followup_question` when a planned segment lacks a non-lead question grounded in an earlier explanation;
- `abrupt_transition` for generic announcer-style resets;
- `mechanical_turn_taking` when a longer script alternates speakers almost perfectly.

Profiles may promote any of these warnings to errors. The included production profiles make missing follow-ups and abrupt transitions fatal.

## Safe evaluation

Automated generation never starts a player or sends sound to speakers. It validates hashes, format, duration, sample rate, channels, byte size, and a complete FFmpeg decode to a null sink. A human voice/personality check is necessarily subjective, so listening UAT is a separate, explicit, owner-initiated action after the automated run has stopped.
