# Personalized Audio Episode Engine

## MVP Product, Functional, Non-Functional, and Technical Specification

**Document status:** Approved for implementation
**Specification date:** August 2, 2026
**Target release:** MVP / proof of concept
**Primary runtime:** Scheduled Codex task operating in a local, version-controlled repository
**Canonical MVP episode:** World, U.S., and Seattle Daily News Briefing
**Primary listener:** Repository owner
**Timezone:** `America/Los_Angeles`

---

# 1. Executive summary

The Personalized Audio Episode Engine is a reusable system for generating source-grounded, conversational podcast episodes about arbitrary topics.

The engine accepts an **episode profile** describing:

* The topic.
* The intended audience.
* Editorial priorities.
* Desired episode structure.
* Required source-collection capability.
* Host and performance style.
* Length and publication settings.

It then coordinates an external source-collection skill, performs editorial selection and planning with Codex, creates a two-host transcript, renders the transcript through Gemini multi-speaker text-to-speech, and publishes the result to a private RSS feed.

The MVP shall implement one canonical profile:

> A calm, fact-first morning briefing covering the most important global, United States, and Seattle-area news.

The MVP intentionally does **not** include Hacker News, calendar, Gmail, messages, or other personalized sources. Those will be added later through separate episode profiles and independently published collector skills.

The core engine must not contain topic-specific collection logic. For example, a future Hacker News API integration must be delivered as a separate collector skill rather than added to the engine repository.

---

# 2. Product vision

The long-term product is not a single news podcast.

It is a personalizable audio-content engine capable of producing recurring episodes on many topics, including:

* General news.
* Technology news.
* Hacker News.
* Personal calendar and planning.
* Research-paper briefings.
* Industry monitoring.
* Sports.
* Local events.
* Saved articles.
* Personal projects.

Each episode type should reuse the same production pipeline while selecting an appropriate source-collection skill and episode profile.

The core product value is:

> Turn relevant information from heterogeneous sources into a trustworthy, concise, natural-sounding audio program that the listener voluntarily consumes.

---

# 3. MVP objective

The MVP must prove the following hypothesis:

> A scheduled Codex workflow, guided by a reusable episode-production skill, can collect current information through an external research skill, select and structure the most important material, generate a natural two-host conversation, synthesize it using Gemini multi-speaker TTS, and publish it to a private podcast feed without manual intervention.

The MVP is successful when one scheduled invocation reliably creates one useful, playable, source-grounded news episode.

---

# 4. Scope

## 4.1 In scope

The MVP includes:

1. A generic episode-profile format.
2. A generic Codex skill for producing audio episodes.
3. Progressive disclosure of stage-specific instructions.
4. Invocation of an external collector skill.
5. A defined collector-output contract.
6. High-recall source collection.
7. One LLM editorial-selection and planning phase.
8. One LLM transcript-writing and directing phase.
9. Two stable hosts, one male and one female.
10. Gemini multi-speaker TTS.
11. TTS segmentation when required by provider guidance.
12. Technical audio concatenation and MP3 encoding.
13. Private RSS publication.
14. A machine-readable run ledger.
15. A concise human-readable run summary.
16. Scheduled execution through Codex.
17. A reproducible Python environment managed with `uv`.
18. Configuration, testing, documentation, and failure recovery.
19. One canonical world/U.S./Seattle news episode profile.
20. One compatible external web-research collector skill.

## 4.2 Explicitly out of scope

The MVP shall not include:

* Hacker News API code.
* Hacker News collection logic.
* Google Calendar.
* Gmail.
* Google Messages.
* SMS or chat applications.
* Personal task management.
* Computer-use workflows.
* Multiple daily episode profiles.
* Batch or parallel episode generation.
* Subagents.
* A graphical dashboard.
* A mobile application.
* Public podcast distribution.
* Spotify publication.
* Audiobookshelf.
* Multiple candidate audio takes.
* Automated audio-quality judging.
* Background music.
* Intro or outro music.
* Loudness mastering.
* Sound effects added during post-production.
* Speaker-track overlap created in post-production.
* A database.
* A vector database.
* A queueing system.
* A web application.
* Cloud orchestration.
* Fine-tuning.
* Long-term automatic preference learning.
* Automatic installation of arbitrary community skills.
* Full article archiving.

---

# 5. Architectural principles

## 5.1 The engine is generic

The core repository must not contain source-specific implementations.

The engine knows how to:

* Request evidence.
* Validate evidence.
* Edit and plan an episode.
* Write and direct a transcript.
* Render speech.
* Publish files.
* Record metrics.

It does not know how to call Hacker News, Gmail, Google Calendar, Reddit, or any other topic-specific source.

## 5.2 Collectors are independent skills

A collector is an independently installable and versioned skill that accepts a collection request and returns an evidence dossier.

Examples include:

* Web deep-research collector.
* Hacker News collector.
* Google Calendar collector.
* Gmail context collector.
* Academic-literature collector.

Collectors may be:

* Existing community skills.
* Organization-owned skills.
* Newly developed skills.
* Skills backed by connectors or MCP servers.

A compatible existing deep-research skill should be reused when possible. If no existing skill satisfies the collector contract, a minimal web-research collector must be implemented and published separately from the engine repository.

## 5.3 One episode per Codex run

Each Codex run processes exactly one episode profile.

The MVP must not generate multiple episode types in one context.

This prevents:

* Cross-topic context pollution.
* Oversized prompts.
* Confusing failures.
* Complex orchestration.
* Unnecessary coupling.

Future schedulers may launch multiple independent episode runs.

## 5.4 Codex is the workflow orchestrator

The Python application handles deterministic operations.

Codex handles judgment-intensive operations:

* Selecting the appropriate collector.
* Reviewing evidence.
* Editorial selection.
* Episode planning.
* Scriptwriting.
* Performance direction.
* Recovering from understandable failures.

Codex must use stable CLI commands and schemas rather than writing new one-off code during each run.

## 5.5 No subagents in MVP

The workflow must execute in one independent Codex run without subagents.

Context management will instead rely on:

* One episode per run.
* Progressive skill disclosure.
* Stage-specific reference files.
* Persisted intermediate artifacts.
* Explicit phase boundaries.
* Concise command output.
* Avoiding unnecessary source reproduction in chat.

Subagents may be evaluated after the single-agent workflow is proven insufficient.

## 5.6 Files are the system of record

Intermediate artifacts, not conversational history, are authoritative.

At each phase, Codex must read the required files and treat them as the source of truth.

The workflow must not rely on the model remembering details from an earlier phase.

## 5.7 Prefer simple, inspectable mechanisms

For the MVP:

* Filesystem over database.
* JSON over custom storage.
* Static RSS over a publishing platform.
* Explicit schemas over informal output.
* Independent skills over a plugin framework built from scratch.
* Scheduled Codex task over a custom orchestration service.
* One canonical episode over a multi-topic platform demonstration.

---

# 6. Validated platform assumptions

Codex supports scheduled tasks that can run against a local project, invoke skills, and start a new independent run each time. Local scheduled tasks require the computer to remain powered on, the desktop application to remain running, and the project directory to remain available.

Codex skills support progressive disclosure: the model initially sees the skill name and description, then loads `SKILL.md`, references, and scripts only when required. Skills may contain scripts, references, assets, and metadata.

GPT-5.6 Sol is OpenAI’s current frontier model for complex professional work. The `gpt-5.6` API alias routes to Sol, although actual Codex model availability may depend on the user’s plan and selected runtime configuration.

Gemini TTS supports controlled multi-speaker generation with up to two configured speakers and natural-language direction for style, accent, pacing, and tone. Google specifically positions this TTS path for exact transcript rendering such as podcasts and audiobooks.

The selected `gemini-3.1-flash-tts-preview` model is a preview model with an 8,192-token input limit. Google warns that quality and voice consistency may drift for outputs longer than a few minutes and recommends dividing longer transcripts into smaller chunks. Google also recommends automated retries for occasional requests that fail because text tokens are returned instead of audio.

Because of that provider guidance, the MVP shall segment an 8–12-minute episode at natural story boundaries. This is a deliberate exception to the original preference for rendering an entire episode in one request.

---

# 7. Users and use cases

## 7.1 Primary user

The primary user is a technically proficient individual who:

* Uses Codex.
* Has a local development environment.
* Wants a private morning audio briefing.
* Values source quality and factual accuracy.
* Prefers calm, concise reporting.
* Wants awareness of meaningful differences in media framing.
* Does not want sensational, exhaustive, or filler-driven coverage.

## 7.2 Primary use case

Each morning, a scheduled Codex task shall:

1. Open the engine repository.
2. Invoke the generic audio-episode skill.
3. Load the canonical news profile.
4. Invoke a compatible external research collector.
5. Generate and publish the episode.
6. Leave a run summary for review.
7. Make the episode available through a private RSS feed consumable in AntennaPod.

## 7.3 Manual use case

The user shall also be able to request:

> Generate today’s episode using the world/U.S./Seattle news profile.

Manual execution must use the same workflow as scheduled execution.

## 7.4 Resume use case

When a run fails, the user or a later Codex run shall be able to resume from the last valid stage instead of repeating successful work.

---

# 8. Canonical MVP episode profile

## 8.1 Purpose

Provide an efficient, calm morning briefing covering the news that an informed Seattle resident should know.

## 8.2 Editorial inspiration

The episode should have the accessibility and focus of a public-radio morning briefing without copying the language, branding, host identities, or exact format of any existing program.

## 8.3 Target duration

* Preferred: 9–11 minutes.
* Acceptable: 7–13 minutes.
* Hard maximum: 15 minutes.
* Do not extend the episode merely to satisfy regional story quotas.

## 8.4 Target coverage

Editorial targets are:

* Two to three global stories.
* Two to three United States stories.
* Zero to two Seattle or Puget Sound stories.
* Hard maximum of seven primary stories.

These are targets, not mandatory quotas.

A regional section may contain fewer stories when:

* No story meets the importance threshold.
* Multiple developments should be combined.
* More stories would make the episode too long.
* Available reporting is weak or uncertain.

## 8.5 Global-news policy

Prioritize:

* War and diplomacy.
* Major elections and government changes.
* International economic developments.
* Major disasters and public-safety events.
* Science and health developments.
* Technology with broad social consequences.
* Important international legal or regulatory actions.
* Events likely to shape public discussion.

Do not over-select:

* Celebrity news.
* Viral social-media stories.
* Incremental political commentary.
* Low-consequence controversies.
* Crime stories without broader importance.
* Stories selected only because they are emotionally intense.

## 8.6 United States policy

Prioritize:

* Federal policy.
* Significant court decisions.
* Elections.
* Economic developments.
* Infrastructure.
* Public health.
* Science and technology.
* National security.
* Major labor or business developments.
* Events with meaningful consequences for many people.

## 8.7 Seattle and local policy

Local includes:

* Seattle.
* King County.
* Puget Sound.
* Washington State when directly relevant to the listener.

Prioritize:

* Significant local or state policy.
* Transportation disruptions or changes with broad impact.
* Major infrastructure issues.
* Public safety developments with community-wide implications.
* Elections and government.
* Education.
* Major economic developments.
* Major cultural or civic events.
* Important changes involving large regional institutions.

Do not include local filler simply to create a local section.

Examples of content that ordinarily does not qualify:

* Small community events.
* Routine weather.
* Individual crime incidents without broader impact.
* Restaurant openings.
* Human-interest filler.
* Ordinary sports scores.
* Routine game summaries.

## 8.8 Local sports policy

Local sports may be included only when the development is materially important, such as:

* A major trade.
* A major signing.
* A major injury.
* A playoff qualification or elimination.
* A championship.
* A major ownership or stadium development.
* A major record.
* A significant organizational controversy.
* A meaningful season-level turning point.

When a sports story qualifies, hosts may briefly contextualize the team’s season.

Routine Mariners, Seahawks, Sounders, Storm, Kraken, or Huskies game recaps do not qualify.

## 8.9 Source policy

The episode must establish a fact-first baseline.

Preferred source hierarchy:

1. Primary documents and official statements.
2. Reuters.
3. Associated Press.
4. Other high-quality factual reporting.
5. Established local reporting for Seattle stories.
6. Specialist sources when subject-matter expertise is required.

Reuters and AP should ordinarily anchor major breaking-news stories when coverage is available.

For consequential stories:

* Use at least two independent sources when practical.
* Distinguish confirmed facts from early reporting.
* Preserve event date and publication date separately.
* Treat casualty figures and similar breaking-news numbers as provisional when appropriate.
* Do not present commentary as reporting.
* Do not use social-media posts as sole factual evidence unless the post is itself the event being reported.

## 8.10 Coverage-divergence policy

The episode may explain differences in outlet coverage when the divergence is materially informative.

The preferred structure is:

1. State the baseline facts on which credible sources agree.
2. Explain which details, implications, or emphasis differ.
3. Avoid assigning simplistic numerical bias scores.
4. Avoid presenting unsupported “both sides” framing.
5. Do not amplify fringe claims merely to create balance.

Coverage divergence must not become a mandatory feature of every story.

## 8.11 Tone

The episode must be:

* Calm.
* Intelligent.
* Concise.
* Conversational.
* Fact-oriented.
* Clear about uncertainty.
* Serious without being stressful.
* Analytical without becoming an opinion program.

It must avoid:

* Doomscroll energy.
* Sensationalism.
* Fake urgency.
* Smugness.
* Partisan cheerleading.
* Excessive hedging.
* Generic AI enthusiasm.
* Repetitive transitions.
* Clickbait language.

---

# 9. End-to-end workflow

The canonical workflow is:

```text
Scheduled Codex task
        │
        ▼
Load generic episode-production skill
        │
        ▼
Load episode profile
        │
        ▼
Create run workspace and collection request
        │
        ▼
Select/invoke external collector skill
        │
        ▼
Receive evidence dossier
        │
        ▼
Validate collector contract
        │
        ▼
Editorial selection + production plan
        │
        ▼
Validate editorial plan
        │
        ▼
Scriptwriting + performance direction
        │
        ▼
Validate script grounding and structure
        │
        ▼
Prepare Gemini TTS segments
        │
        ▼
Render each segment with retry handling
        │
        ▼
Concatenate and encode MP3
        │
        ▼
Generate show notes and transcript
        │
        ▼
Publish episode and update RSS atomically
        │
        ▼
Finalize ledger and run summary
```

---

# 10. Functional requirements

## 10.1 Run initialization

### FR-001

The system shall generate a unique run ID for every execution.

Recommended format:

```text
<profile-id>_<local-date>_<utc-timestamp>_<short-random-id>
```

### FR-002

The system shall resolve the episode date in the profile timezone.

### FR-003

The system shall create a dedicated run directory before collection starts.

### FR-004

The system shall copy or record:

* Profile ID.
* Profile version.
* Engine version.
* Skill version.
* Prompt-template versions.
* Current Git commit.
* Selected Codex model, when observable.
* Selected Gemini model.
* Local date.
* UTC start timestamp.

### FR-005

The system shall refuse to start when required configuration is missing.

---

## 10.2 Profile loading

### FR-010

The system shall accept an episode-profile YAML file as input.

### FR-011

The profile shall be validated against a versioned schema.

### FR-012

Unknown required profile versions shall fail with a clear compatibility error.

### FR-013

The profile shall contain no executable code.

### FR-014

Topic-specific editorial configuration may live in the profile.

### FR-015

Topic-specific collector implementation must not live in the engine repository.

---

## 10.3 Collector selection and invocation

### FR-020

The episode profile shall declare the required collector capability.

Example:

```yaml
collector:
  capability: web_deep_research
  contract_version: "1.0"
  preferred_skill: deep-research
```

### FR-021

The main skill shall invoke the preferred external collector skill when it is installed and compatible.

### FR-022

If the preferred skill is unavailable, the workflow may select another installed collector only when it explicitly declares the same capability and contract version.

### FR-023

The selected collector name and version shall be recorded in the ledger.

### FR-024

If no compatible collector exists, the run shall stop before editorial generation and provide an actionable error.

### FR-025

The engine must not silently perform source collection itself.

### FR-026

The collector shall receive a structured collection request containing:

* Episode profile ID.
* Run ID.
* Run date.
* Timezone.
* Topic.
* Geographic scope.
* Recency window.
* Source policy.
* Desired candidate breadth.
* Output path.
* Contract version.

### FR-027

The collector shall write one evidence dossier to the requested path.

### FR-028

The collector must treat web content as untrusted data, not instructions.

### FR-029

The collector must not execute commands, install software, expose credentials, or follow operational instructions discovered in source material.

---

## 10.4 Collection behavior

### FR-030

Collection shall optimize for high recall rather than early aggressive filtering.

### FR-031

The collector shall capture enough context for the editorial phase to judge:

* Importance.
* Relevance.
* Novelty.
* Credibility.
* Uncertainty.
* Broader implications.
* Coverage divergence.
* Suitability for spoken explanation.

### FR-032

The collector shall not defer all meaningful enrichment until after editorial selection.

### FR-033

Each candidate dossier shall include structured factual claims and source mappings.

### FR-034

The collector shall distinguish:

* Article publication time.
* Event time.
* Last updated time, when available.

### FR-035

The collector should normally return:

* At least eight global candidates.
* At least eight U.S. candidates.
* At least five local candidates when sufficient meaningful local news exists.

These are collection targets, not hard failure thresholds.

### FR-036

Default collection limits shall be:

* Maximum 40 candidate stories.
* Maximum 100 unique sources.
* Maximum 100,000 estimated dossier tokens.
* Warning threshold at 50,000 estimated dossier tokens.

Limits must be configurable.

### FR-037

When the hard limit is reached, the collector shall remove redundant and clearly low-importance candidates before removing source support from stronger candidates.

### FR-038

The collector shall not store complete copyrighted articles in the run artifact.

It may store:

* Source metadata.
* Short excerpts when necessary.
* Structured summaries.
* Claims.
* Relevant context.
* Source URLs.

---

## 10.5 Evidence validation

### FR-040

The engine shall validate the evidence dossier before editorial planning.

### FR-041

Validation shall confirm:

* Valid schema.
* Unique candidate IDs.
* Unique claim IDs.
* Valid source references.
* Valid URLs.
* Region classification.
* Source timestamps where available.
* Non-empty summaries.
* At least one source for every factual claim.
* No path traversal or unexpected file references.

### FR-042

Validation errors shall be returned to Codex in a concise, machine-readable form.

### FR-043

Codex may ask the collector to repair invalid output once.

### FR-044

If repaired output remains invalid, the run shall fail.

---

## 10.6 Editorial selection and planning

### FR-050

Editorial selection and episode planning shall occur in one Codex phase.

### FR-051

This phase shall use:

* The episode profile.
* The complete validated evidence dossier.
* The editorial-planning reference instructions.

### FR-052

The phase shall output a structured editorial plan.

### FR-053

The plan shall identify:

* Selected stories.
* Story order.
* Story region.
* Editorial angle.
* Why each story matters.
* Required claim IDs.
* Optional claim IDs.
* Desired treatment time.
* Lead host.
* Intended host dynamic.
* Coverage-divergence notes, when useful.
* Transition intent.
* Opening approach.
* Closing takeaway.

### FR-054

The editorial phase shall also list excluded candidates and concise exclusion reasons.

Permitted exclusion reasons include:

* Lower importance.
* Duplicate development.
* Weak sourcing.
* Insufficient novelty.
* Outside audience scope.
* Local filler.
* Routine sports result.
* Excessive uncertainty.
* Episode-length constraint.
* Superseded reporting.

### FR-055

The editorial phase shall be performed primarily through one prompt and one structured artifact.

The MVP shall not add:

* Deterministic relevance scoring.
* A separate ranking engine.
* A second editorial model.
* A voting ensemble.
* A hybrid numerical scoring framework.

### FR-056

The editorial phase may select fewer than the target number of stories.

### FR-057

The plan shall not exceed seven primary stories.

### FR-058

The planned episode duration shall not exceed 15 minutes.

---

## 10.7 Editorial-plan validation

### FR-060

The engine shall validate:

* Every selected candidate exists.
* Every referenced claim exists.
* Every selected story has source support.
* No candidate is selected twice.
* Planned duration is valid.
* Regional labels are valid.
* Lead-host values are valid.
* Required fields are present.

### FR-061

A validation failure may be repaired once by Codex.

### FR-062

An unrepaired plan shall stop the run.

---

## 10.8 Script generation

### FR-070

Script generation shall be a separate Codex phase from editorial planning.

### FR-071

The script phase shall receive:

* The validated editorial plan.
* The full validated evidence dossier.
* The episode profile.
* Host profiles.
* Scriptwriting instructions.

### FR-072

The full evidence dossier must remain available to the scriptwriter.

The editorial plan must guide focus but must not become the scriptwriter’s sole factual input.

### FR-073

The script phase shall output:

1. A structured script artifact.
2. A plain-text transcript.
3. Segment boundaries.
4. TTS direction.

### FR-074

The structured script shall identify each turn’s:

* Speaker.
* Spoken text.
* Turn type.
* Supporting claim IDs.
* Story ID.
* Optional performance cue.

### FR-075

Valid turn types shall include:

* `fact`
* `analysis`
* `question`
* `reaction`
* `transition`
* `intro`
* `outro`

### FR-076

Every factual turn shall cite at least one valid claim ID in the structured artifact.

Citations are metadata and shall not be spoken aloud.

### FR-077

Analysis based on reported facts shall reference the relevant claims.

### FR-078

The plain-text transcript shall contain only material intended for TTS plus supported performance annotations.

---

# 11. Host and conversational requirements

## 11.1 Host configuration

### FR-080

The default episode shall use two recurring hosts:

* One female voice.
* One male voice.

### FR-081

Host names and Gemini voices shall be configurable.

### FR-082

The same names and voices shall be used across all MVP episodes unless explicitly changed in configuration.

## 11.2 Host roles

The hosts shall use **flexible symmetry**:

* Both hosts materially contribute.
* Either host may lead a story.
* Lead responsibility should alternate naturally.
* The non-leading host asks useful questions, adds context, tests implications, or reframes the story.
* Neither host exists only to react.
* Neither host monopolizes the episode.

## 11.3 Conversation form

### FR-083

The conversation shall resemble a professionally produced radio or podcast discussion.

### FR-084

A typical story may follow this pattern:

1. One host introduces the development.
2. The other clarifies the central issue.
3. The lead host explains facts and context.
4. The second host probes implications or uncertainty.
5. Both arrive at a concise takeaway.

The pattern must not become rigid or visibly repetitive.

### FR-085

The script shall use:

* Natural spoken syntax.
* Contractions.
* Varied turn length.
* Occasional short reactions.
* Purposeful pauses.
* Natural follow-up questions.
* Smooth handoffs.
* Occasional callbacks.

### FR-086

The script shall avoid:

* “That’s fascinating.”
* “Absolutely.”
* “Great question.”
* Repetitive affirmations.
* Fake surprise.
* Fake personal anecdotes.
* Claims that hosts personally read, attended, experienced, or witnessed events.
* Forced jokes.
* Constant interruptions.
* Excessive stage direction.
* Announcer voice.
* Reading URLs or citation names aloud.
* Talking about being artificial hosts.

### FR-087

Performance tags shall be used sparingly.

Acceptable examples:

```text
[curious]
[brief pause]
[serious]
[slight laugh]
```

Unacceptable default behavior includes theatrical gasping, ominous whispering, exaggerated laughter, or tags on most lines.

---

# 12. Factual-grounding requirements

### FR-090

The structured script shall maintain claim lineage from spoken fact to evidence source.

### FR-091

No factual claim shall be introduced solely because it “sounds plausible.”

### FR-092

Numerical values, dates, names, titles, and causal assertions require explicit source support.

### FR-093

The script shall distinguish:

* Confirmed facts.
* Reported allegations.
* Expert interpretation.
* Host analysis.
* Uncertainty.
* Developing information.

### FR-094

When credible sources disagree, the script shall state the disagreement rather than silently selecting one account.

### FR-095

When coverage differs primarily in emphasis rather than facts, the script shall characterize it as an emphasis difference.

### FR-096

The system shall not manufacture political balance by pairing established facts with unsupported counterclaims.

### FR-097

A deterministic validator shall verify that all referenced story, candidate, source, and claim IDs exist.

### FR-098

The MVP shall not add a third LLM fact-checking pass.

The structured claim ledger, script instructions, and deterministic lineage checks are the v0 safeguards.

---

# 13. Script validation

### FR-100

Validation shall confirm:

* Exactly two configured speakers are used.
* Every turn has a valid type.
* Factual turns contain claim IDs.
* Claim IDs exist.
* Story IDs exist.
* No segment exceeds TTS limits.
* Total estimated duration is within bounds.
* The transcript is non-empty.
* Host names match TTS speaker names exactly.
* No URLs appear in spoken text.
* No source citation syntax appears in spoken text.
* No unsupported third speaker exists.

### FR-101

The validator shall emit warnings for:

* Excessive use of performance tags.
* Excessive reaction-only turns.
* One host speaking more than 70% of words.
* More than three consecutive turns by one host.
* Repeated stock phrases.
* A story lacking a clear takeaway.
* Script duration outside the preferred range.

### FR-102

Warnings do not automatically fail the run unless the profile marks them as fatal.

### FR-103

Codex may repair the script once after validation.

---

# 14. TTS requirements

## 14.1 Provider

### TR-001

The MVP shall use:

```text
gemini-3.1-flash-tts-preview
```

### TR-002

The provider and model shall be configurable behind a speech-renderer interface.

### TR-003

The engine shall not assume that a preview model remains available indefinitely.

## 14.2 Input segmentation

### TR-004

The application shall enforce the model-specific input-token limit before every request.

### TR-005

The default safe prompt limit shall be 7,000 estimated tokens per segment.

### TR-006

The absolute configured limit must not exceed the provider’s documented 8,192-token input limit without a model change.

### TR-007

Because Google warns of quality drift after a few minutes, the system shall segment the transcript at natural boundaries.

Preferred boundaries are:

* Between stories.
* Before the local section.
* Before the closing recap.

### TR-008

A segment should generally represent two to four minutes of speech.

### TR-009

A story should not be split mid-discussion unless required by the input limit.

### TR-010

Every segment shall include:

* Stable host voice assignments.
* Stable host descriptions.
* Stable overall scene description.
* Relevant director notes.
* Exact transcript.
* Segment position.
* Minimal continuity context when necessary.

## 14.3 Rendering

### TR-011

The Gemini request shall configure no more than two speakers.

### TR-012

Speaker names in the request must exactly match transcript speaker names.

### TR-013

The renderer shall save raw returned audio before conversion.

### TR-014

Every segment shall be validated as decodable audio.

### TR-015

The system shall reject output when:

* No audio is returned.
* The response is text.
* Audio duration is implausibly short.
* Audio cannot be decoded.
* The output file is empty.
* The model audibly reads production instructions at the beginning, when detectable through returned metadata or a configured smoke check.

## 14.4 Retry behavior

### TR-016

Each failed segment shall be retried up to three times.

### TR-017

Retries shall use exponential backoff with jitter.

Recommended delays:

* Retry 1: approximately 2 seconds.
* Retry 2: approximately 5 seconds.
* Retry 3: approximately 12 seconds.

### TR-018

A retry shall rerender only the failed segment.

### TR-019

Successful segments shall not be rerendered.

### TR-020

If all retries fail, the episode shall not be published.

### TR-021

The run shall remain resumable from the failed segment.

---

# 15. Audio-processing requirements

### TR-030

Gemini output shall be converted to a standard intermediate WAV representation when necessary.

### TR-031

Segments shall be concatenated in transcript order.

### TR-032

The final publication format shall be MP3.

Recommended default:

* Mono.
* 44.1 kHz or 48 kHz.
* Constant or high-quality variable bitrate suitable for speech.
* MIME type `audio/mpeg`.

### TR-033

FFmpeg shall be used for required technical conversion and concatenation.

### TR-034

The MVP shall not apply creative post-processing.

Specifically, it shall not add:

* Music.
* Sound effects.
* Dynamic-range mastering.
* Artificial overlap.
* Reverb.
* Room tone.
* Compression intended to change performance.
* Voice modification.

### TR-035

Basic format conversion and concatenation do not count as creative post-processing.

### TR-036

The final audio shall be checked with `ffprobe` or equivalent for:

* Duration.
* Codec.
* Sample rate.
* Channel count.
* File size.
* Decode errors.

---

# 16. Publication requirements

## 16.1 Outputs

### FR-110

A successful episode shall publish:

* MP3 audio.
* Plain-text transcript.
* HTML show notes.
* JSON episode metadata.
* RSS feed entry.

### FR-111

Show notes shall include:

* Episode summary.
* Story headings.
* Concise story summaries.
* Sources grouped by story.
* Publication timestamps when relevant.
* A disclosure that the episode was generated with AI.
* The episode-generation date.

### FR-112

Source links shall not be read aloud.

## 16.2 RSS

### TR-040

The engine shall generate a standards-compatible RSS 2.0 podcast feed.

### TR-041

Each item shall include:

* Stable GUID.
* Title.
* Publication date.
* Description.
* Enclosure URL.
* Enclosure MIME type.
* Enclosure byte length.
* Episode duration.
* Transcript URL.
* Show-notes URL.

### TR-042

The feed shall be compatible with AntennaPod.

### TR-043

The canonical episode GUID shall be stable for a given profile and local date.

Recommended GUID input:

```text
<feed-id>:<profile-id>:<YYYY-MM-DD>
```

### TR-044

Rerunning the same profile and date shall update the existing episode rather than create a duplicate.

## 16.3 Hosting

### TR-045

The engine shall publish into a configured static directory.

### TR-046

Configuration shall provide:

* Publish directory.
* Public base URL.
* Feed path.
* Private feed token.
* Feed metadata.

### TR-047

The reference deployment shall expose the static directory over HTTPS through a private or restricted endpoint, such as Tailscale Serve or an equivalent user-controlled static host.

### TR-048

The core application shall not implement a cloud-storage provider in the MVP.

### TR-049

The repository shall include a local static-server command for development testing.

### TR-050

Publication shall use atomic file replacement.

The feed must never temporarily reference a partially written MP3.

## 16.4 Private-feed security

### NFR-001

The feed URL shall contain a cryptographically random, unguessable token.

### NFR-002

The token shall be stored outside version control.

### NFR-003

The MVP may rely on a secret URL because the canonical episode contains public news only.

### NFR-004

The documentation must state that secret-URL privacy is insufficient for future personal calendar, email, or message episodes.

---

# 17. Run ledger and observability

## 17.1 Required artifacts

Every run shall create:

1. `ledger.json`
2. `summary.md`

No metrics database or dashboard is required.

## 17.2 Ledger purpose

The ledger shall make it possible to determine:

* Where time was spent.
* Where context grew.
* Which stage failed.
* Which content was selected.
* How much content was discarded.
* Whether TTS was reliable.
* Whether future collection limits can be reduced.
* Which prompt, profile, collector, and model versions produced the episode.

## 17.3 Run-level fields

### FR-120

`ledger.json` shall contain:

* Run ID.
* Episode key.
* Profile ID and version.
* Engine version.
* Git commit.
* Skill version.
* Collector skill and version.
* Codex model, when observable.
* Gemini model.
* Start and completion timestamps.
* Overall status.
* Failure stage.
* Failure code.
* Failure summary.
* Total elapsed time.
* Output paths.
* Published URLs.

## 17.4 Stage metrics

Each stage shall capture:

* Start time.
* End time.
* Duration.
* Status.
* Retry count.
* Input bytes.
* Input characters.
* Input words.
* Estimated input tokens.
* Output bytes.
* Output characters.
* Output words.
* Estimated output tokens.
* Warning count.
* Error count.

## 17.5 Collection metrics

The ledger shall record:

* Candidates by region.
* Unique sources.
* Sources by publisher.
* Claims.
* Candidates with one source.
* Candidates with multiple sources.
* Candidates with uncertainty flags.
* Dossier character count.
* Estimated dossier tokens.
* Collection duration.
* Collector repair attempts.

## 17.6 Editorial metrics

The ledger shall record:

* Candidates considered.
* Stories selected.
* Stories excluded.
* Selected stories by region.
* Exclusion-reason counts.
* Planned duration.
* Selected source count.
* Selected claim count.
* Percentage of collected claims used.
* Percentage of candidates selected.

## 17.7 Script metrics

The ledger shall record:

* Total words.
* Estimated spoken duration.
* Total turns.
* Turns per host.
* Words per host.
* Host word-share ratio.
* Factual turns.
* Analysis turns.
* Questions.
* Reactions.
* Performance tags.
* Distinct claim IDs referenced.
* Unsupported-reference validation failures.
* Segment count.
* Segment token estimates.

## 17.8 TTS metrics

The ledger shall record:

* Segment count.
* Request count.
* Retries by segment.
* Provider latency by request.
* Input token estimate by segment.
* Returned audio bytes.
* Raw duration by segment.
* Final duration.
* Failed-attempt error codes.
* Final codec and file size.

## 17.9 Publication metrics

The ledger shall record:

* RSS entries before update.
* RSS entries after update.
* Feed-write duration.
* Audio-write status.
* Feed URL.
* HTTP validation status, when enabled.
* Enclosure byte length.
* Whether an existing daily episode was replaced.

## 17.10 Human-readable summary

`summary.md` shall include:

* Overall result.
* Episode title.
* Duration.
* Stories selected.
* Top excluded stories.
* Total runtime.
* Number of sources.
* Approximate context size at major stages.
* TTS retry count.
* Warnings.
* Output and feed location.
* Recommended item to inspect when something appears abnormal.

The summary should normally fit on one screen.

---

# 18. Idempotency and resume behavior

### FR-130

The canonical episode key shall be:

```text
<profile-id>:<local-date>
```

### FR-131

Only one published episode may exist for a canonical episode key.

### FR-132

Every artifact shall be written using a temporary file followed by atomic rename.

### FR-133

The run state shall identify the last completed valid stage.

### FR-134

A resumed run shall reuse validated artifacts unless explicitly instructed to regenerate them.

### FR-135

Supported resume points shall include:

* After collection.
* After editorial planning.
* After script generation.
* After each successful TTS segment.
* Before publication.

### FR-136

Changing the profile, evidence dossier, editorial plan, or script must invalidate dependent downstream artifacts.

### FR-137

Artifact hashes shall be used to identify invalidation.

Example:

* New dossier invalidates plan, script, audio, and publication.
* New plan invalidates script, audio, and publication.
* New script invalidates audio and publication.
* Re-publication alone does not require new audio.

---

# 19. Repository and skill packaging

## 19.1 Core repository

Recommended repository name:

```text
personalized-audio-engine
```

Recommended layout:

```text
personalized-audio-engine/
├── AGENTS.md
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
│
├── .agents/
│   └── skills/
│       └── produce-audio-episode/
│           ├── SKILL.md
│           ├── references/
│           │   ├── workflow.md
│           │   ├── collector-contract.md
│           │   ├── editorial-planning.md
│           │   ├── scriptwriting.md
│           │   ├── tts-rendering.md
│           │   ├── publishing.md
│           │   └── run-ledger.md
│           ├── scripts/
│           │   └── README.md
│           └── agents/
│               └── openai.yaml
│
├── examples/
│   └── profiles/
│       └── world-us-seattle-news.yaml
│
├── schemas/
│   ├── episode-profile.schema.json
│   ├── collection-request.schema.json
│   ├── evidence-dossier.schema.json
│   ├── editorial-plan.schema.json
│   ├── episode-script.schema.json
│   ├── published-episode.schema.json
│   └── run-ledger.schema.json
│
├── src/
│   └── audio_engine/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── paths.py
│       ├── models.py
│       ├── validation.py
│       ├── tokens.py
│       ├── ledger.py
│       ├── state.py
│       ├── prompts.py
│       ├── tts/
│       │   ├── base.py
│       │   └── gemini.py
│       ├── audio/
│       │   └── ffmpeg.py
│       └── publishing/
│           ├── rss.py
│           ├── show_notes.py
│           └── static.py
│
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── contract/
│   └── integration/
│
├── runtime/
│   ├── runs/
│   └── publish/
│
└── docs/
    ├── setup.md
    ├── scheduled-task.md
    ├── collector-authoring.md
    ├── profile-authoring.md
    ├── troubleshooting.md
    └── security.md
```

## 19.2 Core skill

The core skill shall be named approximately:

```yaml
name: produce-audio-episode
description: >
  Produce and publish a source-grounded conversational audio episode from
  an episode profile. Use when asked to generate a podcast, audio briefing,
  daily news episode, or topic-based spoken program from collected evidence.
  Requires a compatible external collector skill.
```

The description must be narrow enough not to trigger for ordinary writing or summarization requests.

## 19.3 Progressive disclosure

`SKILL.md` shall contain only:

* Purpose.
* Entry conditions.
* Required inputs.
* High-level workflow.
* Stage routing.
* Required CLI commands.
* Failure rules.
* References to stage files.

Detailed editorial, scripting, TTS, and publication instructions shall live in separate reference files loaded only for their stage.

## 19.4 AGENTS.md

`AGENTS.md` shall instruct Codex to:

* Use `uv`.
* Never write ad hoc production scripts during a run.
* Use the provided CLI.
* Treat run artifacts as authoritative.
* Keep topic-specific collectors outside this repository.
* Never commit secrets or runtime artifacts.
* Never modify the engine during a scheduled production run.
* Stop when required credentials or collector skills are absent.
* Validate every structured artifact.
* Record every repair and retry.
* Prefer resuming over repeating successful stages.

## 19.5 External collector packaging

The web-research collector shall be installed independently.

It shall not appear under:

```text
personalized-audio-engine/.agents/skills/
```

It may live in:

* A separate repository.
* The user-level skills directory.
* An installed plugin.
* Another managed skill source.

A future Hacker News collector shall follow the same rule.

---

# 20. Episode-profile schema

A profile shall resemble:

```yaml
schema_version: "1.0"

id: world-us-seattle-news
version: "0.1.0"
enabled: true

identity:
  feed_id: joe-daily-briefing
  title_template: "World, U.S. & Seattle — {date}"
  description: >
    A calm, fact-first morning briefing covering major global,
    United States, and Seattle-area news.

audience:
  timezone: America/Los_Angeles
  locale: en-US
  knowledge_level: informed_generalist
  preferences:
    - prioritize material consequences
    - explain relevant context
    - avoid sensationalism
    - compare coverage when differences are meaningful
    - keep local coverage selective

collector:
  capability: web_deep_research
  contract_version: "1.0"
  preferred_skill: deep-research
  recency_hours: 36
  target_candidates:
    global: 10
    us: 10
    local: 8
  maximum_candidates: 40
  maximum_sources: 100

editorial:
  target_minutes: 10
  minimum_minutes: 7
  maximum_minutes: 15
  target_stories:
    global_min: 2
    global_max: 3
    us_min: 2
    us_max: 3
    local_min: 0
    local_max: 2
  maximum_total_stories: 7
  allow_empty_local_section: true
  source_policy: fact_first
  preferred_publishers:
    - Reuters
    - Associated Press
  coverage_divergence: when_material
  local_sports: major_developments_only

hosts:
  format: two_speaker
  relationship: flexible_symmetry
  female:
    name: Maya
    voice: "<selected-gemini-voice>"
    profile: calm, incisive, warm, concise
  male:
    name: Daniel
    voice: "<selected-gemini-voice>"
    profile: curious, analytical, grounded, concise

performance:
  style: calm_public_radio_conversation
  pace: conversational
  use_audio_tags: sparingly
  prohibit_fake_personal_experience: true
  prohibit_urls_in_speech: true

tts:
  provider: gemini
  model: gemini-3.1-flash-tts-preview
  safe_input_tokens: 7000
  target_segment_minutes: 3
  maximum_retries: 3

publishing:
  feed_title: "Joe's Daily Briefing"
  language: en-US
  private_path_env: PODCAST_FEED_TOKEN
  publish_directory_env: PODCAST_PUBLISH_DIR
  base_url_env: PODCAST_BASE_URL
```

---

# 21. Collector contract

## 21.1 Collection request

The engine shall produce:

```json
{
  "contract_version": "1.0",
  "run_id": "world-us-seattle-news_2026-08-03_...",
  "profile_id": "world-us-seattle-news",
  "episode_date": "2026-08-03",
  "timezone": "America/Los_Angeles",
  "topic": "Major global, United States, and Seattle-area news",
  "recency_window": {
    "hours": 36
  },
  "regions": ["global", "us", "seattle_local"],
  "source_policy": {
    "prefer_primary": true,
    "preferred_publishers": ["Reuters", "Associated Press"],
    "multiple_sources_for_consequential_claims": true
  },
  "targets": {
    "global_candidates": 10,
    "us_candidates": 10,
    "local_candidates": 8,
    "maximum_candidates": 40,
    "maximum_sources": 100
  },
  "output_path": "<absolute-run-path>/evidence-dossier.json"
}
```

## 21.2 Evidence dossier

Required top-level fields:

```json
{
  "contract_version": "1.0",
  "collector": {},
  "collection_started_at": "...",
  "collection_completed_at": "...",
  "query_log": [],
  "candidates": [],
  "sources": [],
  "collection_notes": [],
  "warnings": []
}
```

## 21.3 Candidate structure

Each candidate shall contain:

```json
{
  "candidate_id": "story_<stable-id>",
  "headline": "Human-readable headline",
  "region": "global",
  "event_date": "2026-08-02",
  "first_reported_at": "...",
  "last_updated_at": "...",
  "summary": "What happened",
  "context": "Relevant background and history",
  "why_it_matters": "Consequences and audience relevance",
  "current_uncertainty": [
    "Unresolved question"
  ],
  "coverage_notes": {
    "baseline_consensus": "Facts broadly agreed upon",
    "meaningful_differences": [
      "Difference in emphasis or interpretation"
    ]
  },
  "claims": [
    {
      "claim_id": "claim_<id>",
      "text": "Supported factual claim",
      "source_ids": ["source_<id>"],
      "confidence": "high",
      "status": "confirmed"
    }
  ],
  "source_ids": ["source_<id>"],
  "local_relevance": null,
  "sports_classification": null
}
```

## 21.4 Source structure

```json
{
  "source_id": "source_<id>",
  "publisher": "Reuters",
  "title": "Article title",
  "url": "https://...",
  "published_at": "...",
  "updated_at": "...",
  "source_type": "wire",
  "is_primary": false,
  "region": "global",
  "notes": "Optional source-quality note"
}
```

---

# 22. CLI requirements

The package shall expose:

```text
audio-engine doctor
audio-engine run-init
audio-engine validate-profile
audio-engine validate-evidence
audio-engine validate-plan
audio-engine validate-script
audio-engine prepare-tts
audio-engine render
audio-engine publish
audio-engine finalize
audio-engine status
audio-engine serve
```

## 22.1 `doctor`

Must check:

* Python version.
* `uv`.
* Locked dependencies.
* FFmpeg.
* FFprobe.
* Gemini API key.
* Publish directory.
* Base URL.
* Feed token.
* Profile validity.
* Writable runtime directory.
* Compatible collector declaration or installation when detectable.

## 22.2 `run-init`

Creates:

* Run directory.
* State file.
* Collection request.
* Initial ledger.

## 22.3 Validation commands

Must:

* Exit non-zero for fatal validation errors.
* Print concise errors.
* Write full validation reports into the run directory.
* Never mutate the input artifact unless explicitly requested.

## 22.4 `prepare-tts`

Must:

* Convert structured script into provider prompts.
* Calculate segment boundaries.
* Verify voice names.
* Estimate tokens.
* Refuse oversized segments.

## 22.5 `render`

Must:

* Render missing segments only.
* Respect completed segment state.
* Retry failures.
* Produce raw and final audio.
* Update ledger after every request.

## 22.6 `publish`

Must:

* Validate final audio.
* Create show notes.
* Create transcript output.
* Write episode metadata.
* Atomically update RSS.
* Preserve stable GUIDs.

## 22.7 `finalize`

Must:

* Complete ledger.
* Generate summary.
* Mark state successful.
* Print feed and episode locations.

---

# 23. Scheduled Codex task

The scheduled task shall be a standalone task that starts a fresh context each day.

Recommended task prompt:

```text
Use $produce-audio-episode to generate and publish today's episode using
examples/profiles/world-us-seattle-news.yaml.

Run the workflow from the repository root. Use America/Los_Angeles as the
episode timezone. Invoke the compatible collector skill declared by the
profile. Use the repository's existing CLI, schemas, prompts, and scripts.

Do not modify application source code, dependencies, schemas, or profile
configuration during this production run. Resume an incomplete run for the
same profile and date when valid artifacts already exist. Publish only after
all required validations and audio checks pass. Return the contents of the
final human-readable run summary.
```

The task shall:

* Run in the local project rather than an isolated disposable worktree.
* Use workspace-write access.
* Have network access for collection and Gemini.
* Use the narrowest additional permissions required.
* Run once per configured morning schedule.
* Start a new independent run rather than reuse an accumulating conversation.

---

# 24. Model requirements

## 24.1 Codex model

The preferred model is GPT-5.6 Sol or the highest-capability GPT-5.6 model available to the scheduled Codex environment.

The model shall be configurable.

The system shall not assume the exact model ID will remain permanent.

The actual model shall be recorded in the ledger when available.

## 24.2 Model phase separation

Editorial planning and scriptwriting shall be separate phase artifacts even if the same Codex model performs both phases.

The distinction is logical and testable:

* Editorial phase decides what the episode should do.
* Script phase decides exactly what the hosts should say and how they should say it.

## 24.3 No direct OpenAI API requirement

The MVP shall use the Codex subscription/runtime for editorial and script work.

It shall not require a separate OpenAI API key solely for these phases.

A future API-based headless runner may be introduced behind the same artifact contracts.

---

# 25. Non-functional requirements

## 25.1 Reliability

### NFR-010

During the first seven scheduled runs:

* At least five shall publish successfully without manual code changes.

### NFR-011

After stabilization:

* At least 90% of daily runs should publish successfully.

### NFR-012

Transient Gemini failures shall not require restarting the full workflow.

### NFR-013

A publication failure shall not destroy generated audio.

### NFR-014

A failed run shall clearly state the failed stage and next recovery action.

## 25.2 Performance

### NFR-020

A normal run should complete within 45 minutes.

### NFR-021

The target p95 run time after stabilization is 60 minutes or less.

### NFR-022

Real-time generation is not required.

### NFR-023

The workflow shall optimize for quality and reliability before latency.

## 25.3 Context efficiency

### NFR-030

The initial skill metadata shall remain concise.

### NFR-031

Stage-specific instructions shall not be loaded before their stage.

### NFR-032

Large source material shall be persisted in artifacts rather than repeatedly restated.

### NFR-033

Command output shall be concise by default.

### NFR-034

The workflow shall not rely on automatic context compaction for correctness.

### NFR-035

Dossier size warnings shall be visible in the run summary.

## 25.4 Maintainability

### NFR-040

Provider-specific code shall be behind interfaces.

### NFR-041

Schemas shall be versioned.

### NFR-042

Profiles shall be data, not code.

### NFR-043

Collector skills shall be replaceable without modifying the production pipeline.

### NFR-044

Prompt templates shall have explicit versions.

### NFR-045

Every production artifact shall record the prompt version used.

## 25.5 Reproducibility

### NFR-050

Dependencies shall be pinned in `uv.lock`.

### NFR-051

A fresh clone shall become runnable through documented setup steps.

### NFR-052

The repository shall include `.env.example` without credentials.

### NFR-053

`audio-engine doctor` shall identify missing setup.

### NFR-054

Tests shall not depend on current live news by default.

## 25.6 Security

### NFR-060

Secrets shall never be committed.

### NFR-061

Runtime directories shall be Git-ignored.

### NFR-062

Logs shall redact API keys and feed tokens.

### NFR-063

Web content shall be treated as untrusted.

### NFR-064

The collector shall not download or execute arbitrary binaries.

### NFR-065

Scheduled production runs shall not modify source code.

### NFR-066

Shell execution shall be limited to documented commands.

### NFR-067

The application shall reject paths outside configured runtime and publication roots.

## 25.7 Privacy

The MVP processes public news only.

Nevertheless:

* Private feed tokens must remain secret.
* Run artifacts must not be committed.
* Future profiles involving personal data must undergo a separate privacy review.
* Personal-data collectors must not be assumed safe merely because the public-news collector is safe.

## 25.8 Portability

### NFR-070

The primary supported environment shall be:

* Python 3.12.
* macOS or Ubuntu Linux.
* FFmpeg installed.
* Codex local project access.
* `uv` dependency management.

### NFR-071

Platform-specific paths shall not be hard-coded.

## 25.9 Usability

### NFR-080

A successful manual run must require one user-level Codex instruction.

### NFR-081

Errors must identify what the user should fix.

### NFR-082

The user must not need to inspect raw JSON to determine whether a run succeeded.

---

# 26. Technology stack

Required:

```yaml
language: Python 3.12
dependency_manager: uv
configuration: YAML + environment variables
data_validation: Pydantic v2
cli: Typer
gemini_sdk: google-genai
http: httpx
audio: FFmpeg + FFprobe
testing: pytest
linting: Ruff
type_checking: Pyright
storage: local filesystem
publication: static RSS 2.0
```

Permitted supporting dependencies:

* `pydantic-settings`
* `PyYAML`
* `respx`

Avoid adding dependencies when the standard library is sufficient.

---

# 27. State and artifact layout

Recommended:

```text
runtime/
├── runs/
│   └── 2026-08-03/
│       └── world-us-seattle-news/
│           └── <run-id>/
│               ├── state.json
│               ├── collection-request.json
│               ├── evidence-dossier.json
│               ├── evidence-validation.json
│               ├── editorial-plan.json
│               ├── plan-validation.json
│               ├── episode-script.json
│               ├── script-validation.json
│               ├── transcript.txt
│               ├── tts/
│               │   ├── segment-001.txt
│               │   ├── segment-001.wav
│               │   ├── segment-002.txt
│               │   └── segment-002.wav
│               ├── episode.mp3
│               ├── show-notes.html
│               ├── episode.json
│               ├── ledger.json
│               └── summary.md
│
└── publish/
    └── <private-token>/
        ├── feed.xml
        ├── episodes/
        │   └── world-us-seattle-news-2026-08-03.mp3
        ├── transcripts/
        │   └── world-us-seattle-news-2026-08-03.txt
        └── notes/
            └── world-us-seattle-news-2026-08-03.html
```

---

# 28. Testing requirements

## 28.1 Unit tests

Must cover:

* Profile parsing.
* Schema validation.
* Path safety.
* State transitions.
* Artifact hashing.
* Token estimation.
* Segment creation.
* Retry logic.
* RSS generation.
* GUID stability.
* Atomic publication.
* Ledger aggregation.
* Secret redaction.

## 28.2 Contract tests

A fake collector shall test:

* Valid dossier.
* Missing claims.
* Missing sources.
* Invalid IDs.
* Duplicate IDs.
* Unsupported contract version.
* Oversized dossier.
* Malicious paths.
* Source text containing prompt-injection instructions.

## 28.3 TTS tests

Mocked tests shall cover:

* Successful render.
* Empty audio.
* Text instead of audio.
* HTTP 500.
* Rate limiting.
* Retry success.
* Retry exhaustion.
* Resume after one completed segment.
* Invalid voice configuration.
* Oversized TTS prompt.

A live Gemini smoke test shall be available but excluded from default CI.

## 28.4 Publication tests

Must verify:

* Valid RSS XML.
* Correct enclosure length.
* Correct MIME type.
* Stable GUID.
* No duplicate daily item.
* Atomic feed replacement.
* Valid transcript and show-notes paths.
* Feed remains readable after rerun.

## 28.5 Golden fixtures

The repository shall include synthetic, non-current fixtures for:

* Evidence dossier.
* Editorial plan.
* Episode script.
* Ledger.
* RSS feed.

Fixtures must not reproduce full copyrighted news articles.

## 28.6 Manual end-to-end test

The release candidate must demonstrate:

1. A real external research collector is invoked.
2. A current news dossier is created.
3. An editorial plan is generated.
4. A grounded two-host transcript is generated.
5. Gemini produces all segments.
6. The MP3 is assembled.
7. The feed is published.
8. AntennaPod discovers and plays the episode.
9. The transcript and source notes are reachable.
10. A rerun does not create a duplicate.

---

# 29. Acceptance criteria

The MVP is complete only when all criteria below are met.

## AC-001: Generic profile execution

The same engine can load the canonical profile without topic-specific Python code.

## AC-002: External collector boundary

The engine invokes a collector skill installed outside the core repository.

## AC-003: No embedded source integration

The core repository contains no Hacker News, Reuters, AP, Google Calendar, Gmail, or other source-specific API client.

## AC-004: End-to-end scheduled run

One scheduled Codex task produces and publishes the episode without manual intermediate intervention.

## AC-005: Structured evidence

The collector output passes the evidence schema.

## AC-006: High-recall collection

The dossier contains materially more candidates than the final episode selects.

## AC-007: Editorial observability

The ledger records selected and excluded candidate counts and exclusion reasons.

## AC-008: Two-stage editorial production

The run contains separate validated editorial-plan and episode-script artifacts.

## AC-009: Evidence retained for scriptwriting

The script phase has access to both the plan and complete dossier.

## AC-010: Two valuable hosts

Both hosts contribute materially, and neither exceeds 70% of spoken words without a warning.

## AC-011: Claim lineage

Every factual script turn maps to one or more valid evidence claims.

## AC-012: Multi-speaker audio

The final episode audibly contains two stable, distinguishable speakers.

## AC-013: Provider-aware segmentation

The episode is segmented at natural boundaries rather than sent as one long TTS request.

## AC-014: Retry handling

A simulated transient TTS failure succeeds without restarting prior phases.

## AC-015: Private RSS

The episode is available through a private RSS URL and playable in AntennaPod.

## AC-016: Idempotency

Rerunning the same profile and date does not create a duplicate feed item.

## AC-017: Human-readable run result

The user can understand the outcome from `summary.md` without opening JSON.

## AC-018: Reproducible setup

A developer can clone the repository, install dependencies with `uv`, configure documented environment variables, run `doctor`, and complete the manual end-to-end workflow.

## AC-019: Quality baseline

Across three consecutive manually reviewed episodes:

* No clearly unsupported major factual claim is identified.
* Story selection is rated at least 3 out of 5.
* Conversational naturalness is rated at least 3 out of 5.
* Voice consistency is rated at least 3 out of 5.
* Overall usefulness is rated at least 3 out of 5.

## AC-020: Behavioral success

The primary user voluntarily listens to at least two of the first three successful episodes.

---

# 30. Failure behavior

| Failure                        | Required behavior                                             |
| ------------------------------ | ------------------------------------------------------------- |
| Invalid profile                | Fail before collection                                        |
| Collector skill absent         | Fail with installation guidance                               |
| Collector fails                | Preserve request and logs; do not continue                    |
| Dossier invalid                | Permit one repair; otherwise fail                             |
| No important local news        | Continue without local section                                |
| Too few total credible stories | Publish a shorter episode if still useful                     |
| Editorial plan invalid         | Permit one repair; otherwise fail                             |
| Script invalid                 | Permit one repair; otherwise fail                             |
| One TTS segment fails          | Retry only that segment                                       |
| TTS retries exhausted          | Preserve successful segments; do not publish                  |
| MP3 validation fails           | Do not publish                                                |
| Publication fails              | Preserve final audio and permit publication-only resume       |
| Feed endpoint unavailable      | Record warning or fail according to configuration             |
| Scheduled task runs twice      | File lock and episode-key logic prevent duplicate publication |

---

# 31. Product-quality evaluation

After each episode, the user may record:

```yaml
story_selection: 1-5
factual_trust: 1-5
relevance: 1-5
conversational_naturalness: 1-5
voice_consistency: 1-5
pacing: 1-5
length: 1-5
overall_usefulness: 1-5

problems:
  unsupported_claim: false
  important_story_missing: false
  weak_story_included: false
  too_many_stories: false
  too_long: false
  too_short: false
  repetitive_banter: false
  unnatural_reaction: false
  voice_changed: false
  instructions_read_aloud: false
  local_filler: false
  excessive_political_framing: false
```

Feedback storage may be a manually edited YAML or JSON file in the MVP.

Automatic preference learning is deferred.

---

# 32. Implementation sequence

## Phase 1: Repository harness

Build:

* Repository structure.
* `uv` environment.
* Configuration.
* Schemas.
* CLI skeleton.
* State and ledger.
* `doctor`.
* Fixtures.
* Core skill skeleton.
* AGENTS.md.

Exit criterion:

* A synthetic run can progress through all states using fixture artifacts.

## Phase 2: Collector contract

Build:

* Collection request.
* Evidence schema.
* Validation.
* Contract tests.
* External collector installation documentation.

Identify or build the separate web-research collector skill.

Exit criterion:

* The external skill produces a valid real-world dossier.

## Phase 3: Editorial artifacts

Build:

* Editorial reference instructions.
* Editorial-plan schema.
* Scriptwriting instructions.
* Script schema.
* Validators.
* Golden fixtures.

Exit criterion:

* A manual Codex run generates valid plans and scripts from a real dossier.

## Phase 4: Audio

Build:

* Gemini client.
* Voice configuration.
* Segment generation.
* Retry logic.
* Resume logic.
* FFmpeg concatenation.
* MP3 validation.

Before locking voices, generate several 60–90-second test conversations and select the best male/female pairing.

Exit criterion:

* A full episode renders with stable voices.

## Phase 5: Publication

Build:

* Show notes.
* Transcript publication.
* RSS generation.
* Static publisher.
* Atomic writes.
* Local server.
* AntennaPod test.

Exit criterion:

* AntennaPod downloads and plays the episode.

## Phase 6: Scheduled execution

Build:

* Durable scheduled-task prompt.
* Permissions documentation.
* Production-run restrictions.
* Failure-summary behavior.

Exit criterion:

* Three scheduled runs complete with no manual code changes.

---

# 33. Risks and mitigations

## 33.1 “Engine” overdesign

**Risk:** The team builds an abstract platform instead of a working episode.

**Mitigation:** Only implement abstractions required by the canonical news profile. A second collector or profile must not be implemented merely to prove extensibility.

## 33.2 External collector incompatibility

**Risk:** Community research skills do not produce the required dossier.

**Mitigation:** Keep the contract small and explicit. Build a thin separate collector skill only when existing skills cannot satisfy it.

## 33.3 Context bloat

**Risk:** Broad collection makes editorial performance worse.

**Mitigation:** Bound the dossier, record size metrics, use one episode per run, persist artifacts, and progressively load instructions. Do not introduce subagents until measured evidence shows they are needed.

## 33.4 High recall becomes uncontrolled collection

**Risk:** “Capture everything” creates excessive noise and runtime.

**Mitigation:** Use configurable hard limits and collect rich information about a bounded candidate set rather than unlimited raw content.

## 33.5 Editorial quality is weaker than speech quality

**Risk:** The episode sounds polished but is not useful.

**Mitigation:** Evaluate story selection separately from audio naturalness and capture selected/dropped metrics from the first run.

## 33.6 Gemini preview instability

**Risk:** Voice drift, failed requests, or model replacement.

**Mitigation:** Short segments, retries, exact model logging, provider abstraction, and preserved transcripts.

## 33.7 Two-host format feels artificial

**Risk:** Reactions become repetitive or add no value.

**Mitigation:** Flexible symmetry, balanced word share, reaction warnings, and an eventual configurable single-host fallback. The fallback does not need to be implemented in MVP.

## 33.8 Source-grounding failure

**Risk:** Natural dialogue makes unsupported statements sound authoritative.

**Mitigation:** Claim IDs, deterministic lineage checks, high-quality sources, explicit uncertainty, and human evaluation.

## 33.9 Local feed availability

**Risk:** The phone cannot retrieve the feed when the host computer sleeps.

**Mitigation:** Document that the reference host must remain reachable during podcast refresh. Cloud publication is a later option if local availability proves inconvenient.

## 33.10 Prompt injection from research sources

**Risk:** A webpage tells the agent to alter its behavior or expose data.

**Mitigation:** Collector instructions explicitly classify source content as untrusted data; source text cannot authorize commands, tool use, credential access, or workflow changes.

---

# 34. Deferred roadmap

## V0.2

Potential improvements based on measured failures:

* Tune collection limits.
* Improve source deduplication.
* Improve local-source coverage.
* Improve host balance.
* Add better phrase-repetition detection.
* Add optional technical loudness normalization.
* Add single-host fallback.
* Add feed-health checks.

## V1

Potential profile and collector expansion:

* Hacker News collector skill.
* Hacker News episode profile.
* Personal planning profile.
* Google Calendar collector.
* Gmail context collector.
* Multiple independent scheduled episode runs.
* Feed playlist ordering.
* Preference profile.
* Feedback-informed editorial prompts.

## Later

* Google Messages through computer use.
* Soft commitments and “plans in progress.”
* Audio candidate generation and judging.
* More sophisticated cross-source framing analysis.
* Cloud-hosted static publication.
* Encrypted or authenticated personal feeds.
* Subagent-based collection and review.
* Web dashboard.
* Mobile playback interface.

---

# 35. Final implementation directive

The development team shall build a **working vertical slice**, not a generalized media platform.

The required MVP consists of:

1. One generic, profile-driven audio-production engine.
2. One core Codex episode-production skill.
3. One separately installed compatible web-research collector skill.
4. One world/U.S./Seattle news profile.
5. One scheduled Codex workflow.
6. One Gemini multi-speaker renderer.
7. One private RSS feed.
8. One lightweight per-run ledger.

The core repository must remain free of topic-specific source integrations.

The canonical news profile proves the engine, while the collector contract and profile schema preserve a clean path to future topics without requiring those topics to be built now.

This specification supersedes the earlier three-episode and two-episode MVP proposals.
