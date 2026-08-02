# Personalized Audio Episode Engine

## MVP Product, Functional, Non-Functional, and Technical Specification

**Document status:** Approved for implementation
**Specification date:** August 2, 2026
**Target release:** MVP / proof of concept
**Primary runtime:** Scheduled Codex task operating in a local, version-controlled repository
**Primary MVP example episode:** World, U.S., and Seattle Daily News Briefing
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

It then collects source material using the best available research capability, performs editorial selection and planning with Codex, creates a two-host transcript, renders the transcript through Gemini multi-speaker text-to-speech, and publishes the result to a private RSS feed.

The MVP shall exercise the generic harness end to end with one example profile:

> A calm, fact-first morning briefing covering the most important global, United States, and Seattle-area news.

The world/U.S./Seattle briefing is an example input, not a constraint on the engine's schemas, workflow, or skill instructions. Additional example profiles may illustrate topics such as Hacker News, personal planning, research papers, industry monitoring, or local events without requiring those integrations to be implemented in the MVP.

The core engine must not contain topic-specific editorial or collection assumptions. Topic-specific behavior belongs in an episode profile, a collection request, or an optional independently maintained collector skill or tool.

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

Each episode type should reuse the same production pipeline while selecting an appropriate episode profile and collection approach.

The core product value is:

> Turn relevant information from heterogeneous sources into a trustworthy, concise, natural-sounding audio program that the listener voluntarily consumes.

---

# 3. MVP objective

The MVP must prove the following hypothesis:

> A scheduled Codex workflow, guided by a reusable episode-production skill, can collect relevant information using available capabilities or native research, select and structure the most important material, generate a natural two-host conversation, synthesize it using Gemini multi-speaker TTS, and publish it to a private podcast feed without manual intervention.

The initial MVP is successful when scheduled invocations reliably progress through the complete pipeline and create a playable audio file without manual code changes. Editorial usefulness and listening behavior may be reviewed informally, but they are not MVP metrics.

---

# 4. Scope

## 4.1 In scope

The MVP includes:

1. A generic episode-profile format.
2. A generic Codex skill for producing audio episodes.
3. Progressive disclosure of stage-specific instructions.
4. Source collection using available skills or tools, with native Codex research and web search as the default fallback.
5. A defined topic-generic evidence-output contract.
6. High-recall source collection.
7. One LLM editorial-selection and planning phase.
8. One LLM transcript-writing and directing phase.
9. Two stable hosts, one male and one female.
10. Gemini multi-speaker TTS.
11. TTS segmentation when required by provider guidance.
12. Technical audio concatenation and MP3 encoding.
13. Private RSS publication.
14. A machine-readable run-state record.
15. A concise human-readable run summary.
16. Scheduled execution through Codex.
17. A reproducible Python environment managed with `uv`.
18. Configuration, testing, documentation, and failure recovery.
19. One world/U.S./Seattle news example profile exercised end to end.
20. Documentation of optional research skills or tools that may improve collection quality.

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
* A built-in batch or parallel-generation orchestrator. Independently started runs may overlap and must remain safe.
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
* Record durable run state and failures.

It does not know how to call Hacker News, Gmail, Google Calendar, Reddit, or any other topic-specific source.

## 5.2 Collection is agent-directed and capability-aware

The episode-production skill shall tell Codex what evidence is required, not prescribe one collection implementation.

For each run, Codex should use the best relevant capability already available in the environment. Examples include:

* Research or deep-research skills.
* Web-search and browser tools.
* Connectors or MCP servers.
* Topic-specific collectors such as Hacker News, calendar, email, or academic-literature tools.

An episode profile may suggest a preferred capability or skill, but the suggestion is not a hard dependency unless the profile explicitly declares that its source type cannot be collected another way.

When no suitable specialized collector is installed, Codex shall perform the required research itself using its native research and web-search capabilities. The fallback must produce the same validated evidence artifact as any specialized collector.

The README shall list optional skills or tools that may improve collection quality and explain how the user can install or configure them. The production workflow must not install skills automatically.

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

* Selecting the appropriate collection capability or native research fallback.
* Reviewing evidence.
* Editorial selection.
* Episode planning.
* Scriptwriting.
* Performance direction.
* Recovering from understandable failures.

Codex must use the repository's schemas, documented commands, and reusable scripts for repeatable deterministic work rather than writing new one-off production code during each run.

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
* One end-to-end example episode over multiple implemented topic integrations.

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
3. Load the world/U.S./Seattle news example profile.
4. Collect evidence using the best available research capability, falling back to native web research when needed.
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

# 8. Example MVP episode profile: world/U.S./Seattle news

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

## 8.12 Other illustrative episode examples

The repository may include additional example profiles or partial profile snippets to demonstrate that topic and scope are data rather than engine behavior. Illustrative examples include:

* A Hacker News briefing scoped to technically significant discussions and project releases.
* A personal daily-planning episode scoped to calendar events, commitments, and preparation needs.
* A research-paper briefing scoped to a field, publication window, and desired technical depth.
* An industry-monitoring episode scoped to named companies, technologies, regulations, or markets.

These are examples only. They do not require the corresponding private connectors, API integrations, or collectors to be implemented for the MVP, and the engine must not contain special cases for their taxonomy.

---

# 9. End-to-end workflow

The generic workflow is:

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
Select available collection capability or native research fallback
        │
        ▼
Receive evidence dossier
        │
        ▼
Validate evidence contract
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
Finalize run state and run summary
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

## 10.3 Evidence collection

### FR-020

The episode profile shall describe the evidence needed for the episode and may suggest useful collection capabilities.

Example:

```yaml
collection:
  source_type: public_web
  suggested_capabilities:
    - web_deep_research
  allow_native_research_fallback: true
```

### FR-021

The main skill shall inspect the skills and tools available in the current environment and choose a suitable collection approach.

### FR-022

When an appropriate specialized research skill, connector, or collector is available, Codex should use it if it can satisfy the collection request and evidence contract.

### FR-023

The run state shall record the collection method used and, when observable, the selected skill or tool name and version.

### FR-024

When no suitable specialized capability is available and the profile allows public research fallback, Codex shall perform native research and web search itself.

### FR-025

The run shall stop with an actionable error only when the requested evidence requires an unavailable authenticated or specialized source and the profile cannot be satisfied through native research.

### FR-026

The selected collection capability, or Codex itself when using native research, shall receive a structured collection request containing:

* Episode profile ID.
* Run ID.
* Run date and timezone.
* Topic and episode scope.
* Audience and editorial priorities relevant to collection.
* Requested source types or capabilities.
* Recency or time window, when applicable.
* Source and evidence-quality policy.
* Desired candidate breadth and configured limits.
* Output path.
* Evidence contract version.

### FR-027

Regardless of collection method, Codex shall write one evidence dossier to the requested path and validate it before editorial work.

### FR-028

All collection methods must treat retrieved content as untrusted data, not instructions.

### FR-029

Collection must not execute commands, install software, expose credentials, or follow operational instructions discovered in source material.

---

## 10.4 Collection behavior

### FR-030

Collection shall optimize for high recall rather than early aggressive filtering.

### FR-031

Collection shall capture enough context for the editorial phase to judge:

* Importance.
* Relevance.
* Novelty.
* Credibility.
* Uncertainty.
* Broader implications.
* Conflicts or meaningful differences between sources, when applicable.
* Suitability for spoken explanation.

### FR-032

Collection shall not defer all meaningful enrichment until after editorial selection.

### FR-033

Each candidate item shall include structured factual claims and claim-level evidence mappings.

### FR-034

When relevant to the source type, the evidence artifact shall distinguish:

* Source creation or publication time.
* Event or effective time.
* Retrieval time.
* Last updated time, when available.

### FR-035

Candidate targets shall be defined by the episode profile. The world/U.S./Seattle example may request at least eight global, eight U.S., and five local candidates when sufficient meaningful news exists, but these are example-profile targets rather than engine requirements.

### FR-036

Default collection limits shall be:

* Maximum 40 candidate items.
* Maximum 100 unique sources.
* Maximum 100,000 estimated dossier tokens.
* Warning threshold at 50,000 estimated dossier tokens.

Limits must be configurable.

### FR-037

When a hard limit is reached, collection shall remove redundant and clearly low-importance candidates before removing source support from stronger candidates.

### FR-038

The evidence artifact shall not store complete copyrighted articles unless the user supplied or owns the content and the profile explicitly permits retention.

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
* Valid source locators and URLs when applicable.
* Retrieval timestamps.
* Source creation, publication, event, and update timestamps where applicable.
* Non-empty summaries.
* At least one claim-level evidence mapping for every factual claim.
* A short supporting excerpt or precise primary-source locator for every factual claim eligible for editorial selection.
* Canonical source locator and access status.
* Source content hash when the retrieved representation is available.
* Direct, attributed, inferred, or disputed support classification.
* Required attribution, uncertainty, and qualification text.
* Original-reporting or syndication relationship when multiple web sources are presented as independent support.
* No path traversal or unexpected file references.

### FR-042

Validation errors shall be returned to Codex in a concise, machine-readable form.

### FR-043

Codex may repair the collection output or repeat the affected collection step once.

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

* Selected candidates or planned episode segments.
* Segment order.
* Optional profile-defined section or classification.
* Editorial angle.
* Why each selected candidate or segment matters.
* Required claim IDs.
* Optional claim IDs.
* Desired treatment time.
* Lead host.
* Intended host dynamic.
* Source-conflict or comparison notes, when useful.
* Transition intent.
* Opening approach.
* Closing takeaway.

### FR-054

The editorial phase shall also list excluded candidates and concise exclusion reasons.

Example exclusion reasons include:

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

Profiles may define additional reason codes. The engine schema must not hard-code news regions, sports categories, or other topic-specific taxonomy.

### FR-055

The editorial phase shall be performed primarily through one prompt and one structured artifact.

The MVP shall not add:

* Deterministic relevance scoring.
* A separate ranking engine.
* A second editorial model.
* A voting ensemble.
* A hybrid numerical scoring framework.

### FR-056

The editorial phase may select fewer than the profile's target number of items or segments.

### FR-057

The plan shall not exceed the maximum item or segment count configured by the profile.

### FR-058

The planned episode duration shall remain within the duration bounds configured by the profile.

---

## 10.7 Editorial-plan validation

### FR-060

The engine shall validate:

* Every selected candidate exists.
* Every referenced claim exists.
* Every selected candidate or planned segment has source support when it contains factual material.
* No candidate is selected twice.
* Planned duration is valid.
* Profile-defined sections or classifications are valid when present.
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
* Candidate ID and planned-segment ID when applicable.
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
* Either host may lead a planned segment.
* Lead responsibility should alternate naturally.
* The non-leading host asks useful questions, adds context, tests implications, or reframes the segment topic.
* Neither host exists only to react.
* Neither host monopolizes the episode.

## 11.3 Conversation form

### FR-083

The conversation shall resemble a professionally produced radio or podcast discussion.

### FR-084

A typical planned segment may follow this pattern:

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

The structured script shall maintain claim lineage from each spoken fact through a normalized claim and its claim-level evidence mapping to the underlying source.

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

A deterministic validator shall verify that all referenced planned-segment, candidate, source, claim, and claim-support IDs exist and that required evidence fields are present.

### FR-098

The MVP shall not add a third LLM fact-checking pass.

The structured evidence mappings, script instructions, and deterministic lineage checks are the v0 safeguards. Referential validation does not prove semantic truth; the stored excerpt or source locator must make every selected factual claim directly auditable from the run artifact.

---

# 13. Script validation

### FR-100

Validation shall confirm:

* Exactly two configured speakers are used.
* Every turn has a valid type.
* Factual turns contain claim IDs.
* Claim IDs exist.
* Candidate and planned-segment IDs exist when referenced.
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
* A planned segment lacking a clear takeaway.
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

* Between planned segments.
* Between profile-defined sections.
* Before the closing recap.

### TR-008

A segment should generally represent two to four minutes of speech.

### TR-009

A planned segment should not be split mid-discussion unless required by the input limit.

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
* Planned-segment headings.
* Concise segment summaries.
* Sources grouped by planned segment or candidate.
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

The MVP may rely on a secret URL because the primary example episode contains public news only.

### NFR-004

The documentation must state that secret-URL privacy is insufficient for future personal calendar, email, or message episodes.

---

# 17. Run state and result summary

## 17.1 Required artifacts

Every invocation that acquires episode ownership shall create:

1. `state.json`
2. `summary.md`

The MVP shall not collect product analytics, aggregate performance metrics, token counters, source-count dashboards, or listening metrics.

## 17.2 Run-state purpose

The run state exists only to:

* Identify the episode and active run.
* Record which stages completed successfully.
* Locate and validate persisted artifacts for resume.
* Explain the stage and reason for a failure.
* Confirm whether a valid final audio file was created and whether it was published.

### FR-120

`state.json` shall contain only operational state needed for correctness and recovery:

* Run ID and episode key.
* Profile ID and version.
* Engine Git commit and skill version.
* Collection method and selected skill or tool when observable.
* Codex and Gemini models when observable.
* Start and completion timestamps.
* Current stage and last completed valid stage.
* Overall status.
* Failure stage, code, and concise recovery guidance.
* Artifact paths and hashes.
* Final-audio validation result.
* Publication status and redacted published locations.

Stage attempts may retain concise errors required for retry or diagnosis, but the engine shall not add counters solely for analytics.

## 17.3 Human-readable summary

`summary.md` shall include:

* Overall result.
* Episode title.
* Last completed stage.
* Whether a valid audio file was created.
* Whether publication succeeded.
* Failure and recovery guidance when applicable.
* Output and redacted feed locations.
* Warnings that require inspection.

The summary should normally fit on one screen.

---

# 18. Idempotency, concurrency, and resume behavior

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

### FR-138

Before selecting, creating, resuming, or mutating a run, the initialization script shall atomically create an episode lease for the episode key using exclusive file creation.

Recommended lock path:

```text
runtime/locks/episode-<sha256-of-episode-key>.json
```

The lease shall contain the owning run ID, episode key, creation time, and last heartbeat time. Every script that mutates run state shall verify the owning run ID and refresh the heartbeat as part of its atomic state update. The lease remains effective across the separate commands and agent-driven phases in one Codex run.

### FR-139

If a current episode lease already exists, the second invocation shall exit without creating or mutating run artifacts and report that the episode is already in progress. This is a successful no-op rather than a pipeline failure.

A lease may be recovered only when its owner is in a terminal state or its heartbeat is older than a configurable maximum run age. Recovery shall atomically rename the old lease to a quarantined stale filename and then retry exclusive creation; concurrent recoverers still converge on one owner. A process may remove or refresh a live lease only when its run ID matches the recorded owner. Normal finalization or handled failure shall persist terminal state before releasing the lease; an unexpected crash relies on stale recovery.

### FR-140

Because publication occurs inside one script process, that script shall acquire a separate non-blocking or bounded-wait OS advisory lock keyed by feed ID before reading or updating the feed:

```text
runtime/locks/feed-<sha256-of-feed-id>.lock
```

The publisher shall re-read the current feed only after acquiring the feed lock, write and validate episode assets first, atomically replace the feed last, and then release the feed lock. This allows different episodes to render concurrently while serializing the short feed read-modify-write operation. If the feed lock cannot be obtained within the configured short timeout, publication shall be marked deferred and remain resumable without rerendering audio.

### FR-141

Lock ordering shall always be episode lease ownership followed by feed lock acquisition. Code shall never claim an episode lease while holding a feed lock. This avoids deadlock without introducing a queue or database.

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
│           │   ├── evidence-collection.md
│           │   ├── editorial-planning.md
│           │   ├── scriptwriting.md
│           │   ├── tts-rendering.md
│           │   ├── publishing.md
│           │   └── run-state.md
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
│   └── run-state.schema.json
│
├── scripts/
│   ├── doctor.py
│   ├── init_run.py
│   ├── validate_artifact.py
│   ├── prepare_tts.py
│   ├── render_audio.py
│   ├── publish_episode.py
│   ├── finalize_run.py
│   └── serve_publish_dir.py
│
├── src/
│   └── audio_engine/
│       ├── __init__.py
│       ├── config.py
│       ├── paths.py
│       ├── models.py
│       ├── validation.py
│       ├── tokens.py
│       ├── state.py
│       ├── locks.py
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
│   ├── locks/
│   ├── runs/
│   └── publish/
│
└── docs/
    ├── setup.md
    ├── scheduled-task.md
    ├── optional-collectors.md
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
  daily news episode, or topic-based spoken program. Use available research
  skills and tools when helpful, with native research as the fallback.
```

The description must be narrow enough not to trigger for ordinary writing or summarization requests.

## 19.3 Progressive disclosure

`SKILL.md` shall contain only:

* Purpose.
* Entry conditions.
* Required inputs.
* High-level workflow.
* Stage routing.
* Documented commands and reusable-script routing.
* Failure rules.
* References to stage files.

Detailed editorial, scripting, TTS, and publication instructions shall live in separate reference files loaded only for their stage.

## 19.4 AGENTS.md

`AGENTS.md` shall instruct Codex to:

* Use `uv`.
* Never write ad hoc production scripts during a run.
* Use the documented `uv run python scripts/...` commands for repeatable deterministic work.
* Treat run artifacts as authoritative.
* Keep the engine schemas and workflow topic-generic.
* Never commit secrets or runtime artifacts.
* Never modify the engine during a scheduled production run.
* Use available research skills or tools when appropriate and fall back to native research unless the profile requires an unavailable authenticated source.
* Validate every structured artifact.
* Record every repair and retry.
* Prefer resuming over repeating successful stages.

## 19.5 Optional collection capabilities

The engine repository does not require a separately packaged collector for public-web episodes. Native Codex research and web search are the default fallback.

Optional specialized collectors may live in a separate repository, the user-level skills directory, an installed plugin, a connector, an MCP server, or another managed source. The README shall provide a non-required list of potentially useful research capabilities and setup guidance. Examples must be clearly labeled as suggestions rather than production dependencies.

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

episode:
  topic: Major global, United States, and Seattle-area news
  scope:
    sections:
      - id: global
        description: Material international developments
      - id: us
        description: Material United States developments
      - id: local
        description: Selective Seattle, King County, Puget Sound, or directly relevant Washington State developments
    exclude:
      - low-consequence celebrity or viral stories
      - routine crime, weather, sports scores, and local filler

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

collection:
  source_types:
    - public_web
  suggested_capabilities:
    - web_deep_research
  allow_native_research_fallback: true
  evidence_contract_version: "1.0"
  time_window:
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
  target_sections:
    global:
      minimum_items: 2
      maximum_items: 3
    us:
      minimum_items: 2
      maximum_items: 3
    local:
      minimum_items: 0
      maximum_items: 2
  maximum_total_items: 7
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

`global`, `us`, and `local` are identifiers defined by this example profile. The profile schema shall allow arbitrary topic, scope, section, candidate-target, and exclusion identifiers without teaching the engine what those identifiers mean.

---

# 21. Evidence-collection contract

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
  "scope": {
    "sections": ["global", "us", "local"],
    "notes": "Profile-defined scope; the engine does not interpret these identifiers"
  },
  "time_window": {
    "hours": 36
  },
  "source_types": ["public_web"],
  "suggested_capabilities": ["web_deep_research"],
  "allow_native_research_fallback": true,
  "source_policy": {
    "prefer_primary": true,
    "preferred_publishers": ["Reuters", "Associated Press"],
    "multiple_sources_for_consequential_claims": true
  },
  "targets": {
    "by_section": {
      "global": 10,
      "us": 10,
      "local": 8
    },
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
  "collection_method": {
    "type": "native_research",
    "name": "Codex web research",
    "version": null
  },
  "collection_started_at": "...",
  "collection_completed_at": "...",
  "candidates": [],
  "claims": [],
  "claim_supports": [],
  "sources": [],
  "collection_notes": [],
  "warnings": []
}
```

## 21.3 Candidate structure

Each candidate shall contain:

```json
{
  "candidate_id": "item_<stable-id>",
  "title": "Human-readable candidate title",
  "classification": {
    "section": "profile-defined-section-id",
    "tags": ["profile-defined-tag"]
  },
  "relevant_times": {
    "event_at": "...",
    "effective_at": null,
    "first_reported_at": "...",
    "last_updated_at": "..."
  },
  "summary": "What the candidate is about",
  "context": "Relevant background and history",
  "why_it_matters": "Consequences and audience relevance",
  "uncertainties": [
    "Unresolved question"
  ],
  "source_differences": {
    "baseline_consensus": "Facts broadly agreed upon",
    "meaningful_differences": [
      "Difference in emphasis or interpretation"
    ]
  },
  "claim_ids": ["claim_<id>"],
  "source_ids": ["source_<id>"]
}
```

Candidate classifications and relevant-time fields are optional unless the profile requires them. Their keys and values are profile-defined.

## 21.4 Claim structure

```json
{
  "claim_id": "claim_<id>",
  "candidate_id": "item_<stable-id>",
  "text": "Precisely scoped factual claim",
  "status": "confirmed",
  "confidence": "high",
  "support_ids": ["support_<id>"],
  "required_attribution": "According to the named source, when required",
  "qualifications": ["Material uncertainty or limitation that must be preserved"]
}
```

## 21.5 Claim-support structure

Every factual claim shall have at least one claim-support record.

```json
{
  "support_id": "support_<id>",
  "claim_id": "claim_<id>",
  "source_id": "source_<id>",
  "support_type": "direct",
  "evidence": {
    "excerpt": "Short source text that directly supports the claim",
    "locator": "Page, section, paragraph, timestamp, message ID, event ID, or other precise locator"
  },
  "required_attribution": null,
  "qualifications": [],
  "source_relationship": {
    "originality": "original_reporting",
    "independence_group": "reporting_cluster_<id>"
  }
}
```

`support_type` shall be one of `direct`, `attributed`, `inferred`, or `disputed`. An excerpt may be omitted only when a precise primary-source locator is sufficient and retrievable. Multiple sources in the same independence group must not be counted as independent corroboration.

## 21.6 Source structure

```json
{
  "source_id": "source_<id>",
  "source_type": "web_article",
  "creator_or_publisher": "Reuters",
  "title": "Source title",
  "canonical_locator": "https://... or connector/resource identifier",
  "access_status": "retrieved",
  "retrieved_at": "...",
  "created_at": null,
  "published_at": "...",
  "updated_at": "...",
  "content_hash": "sha256:<hash-of-retrieved-representation>",
  "is_primary": false,
  "originality": {
    "kind": "original_reporting",
    "independence_group": "reporting_cluster_<id>"
  },
  "notes": "Optional source-quality note"
}
```

`canonical_locator` may be a URL, connector resource identifier, or another source-type-appropriate locator. A filesystem locator must remain within an explicitly allowed input root. `content_hash` may be null only when the collection capability does not expose the retrieved representation; the reason must be recorded in `notes`.

---

# 22. Documented commands and reusable scripts

The MVP shall not create a custom `audio-engine` CLI. Repeatable deterministic operations shall be implemented as small repository scripts or library functions and invoked through documented commands.

Recommended command form:

```text
uv sync --locked
uv run python scripts/doctor.py --profile <profile-path>
uv run python scripts/init_run.py --profile <profile-path>
uv run python scripts/validate_artifact.py --type <profile|evidence|plan|script> --input <path>
uv run python scripts/prepare_tts.py --run <run-path>
uv run python scripts/render_audio.py --run <run-path>
uv run python scripts/publish_episode.py --run <run-path>
uv run python scripts/finalize_run.py --run <run-path>
uv run python scripts/serve_publish_dir.py
```

The exact script grouping may be simplified during implementation. The important requirement is that common validation, audio preparation, rendering, publication, and state-update logic be reusable rather than reimplemented by Codex during each run.

The README and skill references shall include copy-pasteable commands for environment setup, validation, rendering, publication, resume, and local feed serving. They may also document direct third-party commands such as `ffmpeg` or `ffprobe` when those are the simplest stable interface.

All scripts shall:

* Provide `--help` and explicit path arguments.
* Exit non-zero for fatal errors.
* Print concise results suitable for an agent run.
* Write detailed validation or error artifacts into the run directory when useful for recovery.
* Avoid mutating source inputs unless the command explicitly owns the output.
* Update `state.json` only after an output is durably written and validated.

## 22.1 Environment check

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
* Availability of native web research or any profile-required authenticated source capability when detectable.

## 22.2 Run initialization

Creates:

* Run directory.
* Collection request.
* Initial state.

## 22.3 Validation scripts

Must:

* Exit non-zero for fatal validation errors.
* Print concise errors.
* Write full validation reports into the run directory when a report is needed for repair.
* Never mutate the input artifact unless explicitly requested.

## 22.4 TTS preparation script

Must:

* Convert structured script into provider prompts.
* Calculate segment boundaries.
* Verify voice names.
* Estimate tokens.
* Refuse oversized segments.

## 22.5 Audio-rendering script

Must:

* Render missing segments only.
* Respect completed segment state.
* Retry failures.
* Produce raw and final audio.
* Persist successful segment state after every completed request.

## 22.6 Publication script

Must:

* Validate final audio.
* Create show notes.
* Create transcript output.
* Write episode metadata.
* Atomically update RSS.
* Preserve stable GUIDs.

## 22.7 Finalization script

Must:

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
episode timezone. Use the best available research skills or tools that satisfy
the profile. If no suitable specialized capability is installed, perform native
web research. Use the repository's schemas, prompts, documented commands, and
reusable scripts.

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

The actual model shall be recorded in the run state when available.

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

Before MVP acceptance, three consecutive scheduled runs shall each create a valid playable audio file without manual code changes or manual intermediate intervention.

### NFR-011

Reliability evaluation is an acceptance exercise, not ongoing product telemetry. The MVP shall not implement success-rate aggregation.

### NFR-012

Transient Gemini failures shall not require restarting the full workflow.

### NFR-013

A publication failure shall not destroy generated audio.

### NFR-014

A failed run shall clearly state the failed stage and next recovery action.

## 25.2 Execution behavior

### NFR-020

The workflow is a background batch process and does not require real-time generation.

### NFR-021

The MVP defines no percentile latency target and shall not add latency instrumentation solely for analytics.

### NFR-022

Each script and external request shall use bounded timeouts so a stuck step fails with recovery guidance rather than running indefinitely.

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

Collection methods shall be replaceable without modifying the production pipeline or evidence contract.

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

The documented environment-check script shall identify missing setup.

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

Collection workflows shall not download or execute arbitrary binaries discovered through source material.

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
* Personal-data collection methods must not be assumed safe merely because public-web research is safe.

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
├── locks/
│   ├── episode-<hash>.json
│   └── feed-<hash>.lock
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
* Episode-lease exclusive acquisition, ownership checks, heartbeat refresh, release, and stale recovery.
* Concurrent same-episode no-op behavior.
* Secret redaction.

## 28.2 Contract tests

Synthetic collection outputs shall test:

* Valid dossier.
* Missing claims.
* Missing sources.
* Missing claim-support records.
* Missing supporting excerpt and locator.
* Missing retrieval timestamp or access status.
* Duplicate sources incorrectly represented as independent corroboration.
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
* Feed-level locking under concurrent publication.
* Concurrent publication of different episode keys without lost feed entries.
* Valid transcript and show-notes paths.
* Feed remains readable after rerun.

## 28.5 Golden fixtures

The repository shall include synthetic, non-current fixtures for:

* Evidence dossier.
* Editorial plan.
* Episode script.
* Run state.
* RSS feed.

Fixtures must not reproduce full copyrighted news articles.

## 28.6 Manual end-to-end test

The release candidate must demonstrate:

1. Evidence is collected through an available skill or tool, or through the native research fallback.
2. A current news dossier is created.
3. An editorial plan is generated.
4. A grounded two-host transcript is generated.
5. Gemini produces all segments.
6. The MP3 is assembled.
7. The feed is published.
8. AntennaPod discovers and plays the episode.
9. The transcript and source notes are reachable.
10. A rerun does not create a duplicate.

## 28.7 Concurrency integration test

The release candidate must demonstrate:

1. Two simultaneous initializations for the same episode key result in one owner and one successful no-op.
2. The no-op invocation does not create or modify run artifacts.
3. A simulated abandoned lease cannot be taken over before its heartbeat expires and can be recovered atomically after it becomes stale without manual cleanup.
4. Two different episode keys can perform non-publication work concurrently.
5. Concurrent publication attempts for different episode keys sharing one feed are serialized and preserve both feed entries.

---

# 29. Acceptance criteria

The MVP is complete only when all criteria below are met.

## AC-001: Generic profile execution

The same harness can load a profile containing arbitrary topic, scope, section, and taxonomy values without topic-specific Python code or news-specific engine validation.

## AC-002: Flexible collection with native fallback

The episode skill uses a suitable available research skill or tool when helpful and completes public-web collection through native research when no specialized collector is installed.

## AC-003: No embedded source integration

The core repository contains no Hacker News, Reuters, AP, Google Calendar, Gmail, or other source-specific API client.

## AC-004: End-to-end scheduled run

One scheduled Codex task produces and publishes the episode without manual intermediate intervention.

## AC-005: Structured evidence

The evidence output passes the same topic-generic schema regardless of whether collection used a skill, connector, tool, or native research.

## AC-006: High-recall collection

The dossier contains materially more candidates than the final episode selects.

## AC-007: Auditable claim support

Every selected factual claim has a valid claim-support record with a source, support type, retrieval provenance, required qualifications, and a supporting excerpt or precise primary-source locator.

## AC-008: Two-stage editorial production

The run contains separate validated editorial-plan and episode-script artifacts.

## AC-009: Evidence retained for scriptwriting

The script phase has access to both the plan and complete dossier.

## AC-010: Two valuable hosts

Both hosts contribute materially to the episode according to the profile's requested conversational format.

## AC-011: Claim lineage

Every factual script turn maps through one or more valid evidence claims and claim-support records to an underlying source.

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

A developer can clone the repository, install dependencies with `uv`, configure documented environment variables, run the documented environment-check script, and complete the manual end-to-end workflow.

## AC-019: Initial pipeline reliability

Three consecutive scheduled runs each create a valid playable audio file without manual code changes or manual intermediate intervention. Publication failures may be diagnosed separately, but they must not destroy the successfully generated audio.

## AC-020: Safe concurrent execution

When two processes start the same episode key concurrently, exactly one owns and mutates the run while the other exits as a successful no-op. When different episodes publish concurrently to the same feed, feed-level locking preserves both entries without corruption or lost updates.

---

# 30. Failure behavior

| Failure                        | Required behavior                                             |
| ------------------------------ | ------------------------------------------------------------- |
| Invalid profile                | Fail before collection                                        |
| Suggested collector skill absent | Use another suitable capability or native research fallback |
| Profile-required authenticated source absent | Fail with configuration guidance before editorial work |
| Specialized collection fails   | Preserve request and errors; use native fallback when allowed |
| Dossier invalid                | Permit one repair; otherwise fail                             |
| No qualifying content for an optional profile section | Continue without that section                   |
| Too few total credible candidates | Publish a shorter episode if still useful                  |
| Editorial plan invalid         | Permit one repair; otherwise fail                             |
| Script invalid                 | Permit one repair; otherwise fail                             |
| One TTS segment fails          | Retry only that segment                                       |
| TTS retries exhausted          | Preserve successful segments; do not publish                  |
| MP3 validation fails           | Do not publish                                                |
| Publication fails              | Preserve final audio and permit publication-only resume       |
| Feed lock remains busy         | Preserve final audio; defer and permit publication-only resume |
| Feed endpoint unavailable      | Record warning or fail according to configuration             |
| Same episode starts twice      | Episode-key lock grants one owner; the other run is a no-op    |
| Different episodes publish together | Feed lock serializes feed updates without blocking rendering |

---

# 31. MVP evaluation

MVP evaluation is limited to the functional and reliability acceptance criteria in this specification, especially successful creation of a valid playable audio file through the complete scheduled pipeline.

The user may review episodes informally, but the MVP shall not define or store numerical quality ratings, listening analytics, structured feedback metrics, or automatic preference learning.

---

# 32. Implementation sequence

## Phase 1: Repository harness

Build:

* Repository structure.
* `uv` environment.
* Configuration.
* Schemas.
* Reusable script and library-function skeleton.
* State and advisory locks.
* Environment-check script.
* Fixtures.
* Core skill skeleton.
* AGENTS.md.

Exit criterion:

* A synthetic run can progress through all states using fixture artifacts.

## Phase 2: Evidence-collection contract

Build:

* Collection request.
* Evidence schema.
* Validation.
* Contract tests.
* Native research fallback instructions.
* README suggestions for optional research skills, tools, connectors, or collectors.

Exit criterion:

* A native research run produces a valid real-world dossier, and the same contract can accept output produced through an available specialized research capability.

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

**Mitigation:** Keep the harness, schemas, and skill instructions topic-generic while implementing only the stages needed for the first end-to-end example. Example profile fields must not become engine taxonomy or validation rules.

## 33.2 Specialized collection capability unavailable or incompatible

**Risk:** An installed research skill or tool is absent, incompatible, or does not produce the required evidence artifact.

**Mitigation:** The main skill adapts useful collected material into the generic evidence contract and falls back to native Codex research and web search for public sources. Only profiles requiring unavailable authenticated sources fail.

## 33.3 Context bloat

**Risk:** Broad collection makes editorial performance worse.

**Mitigation:** Bound the dossier, use one episode per run, persist artifacts, and progressively load instructions. Do not introduce subagents until observed failures show they are needed.

## 33.4 High recall becomes uncontrolled collection

**Risk:** “Capture everything” creates excessive noise and runtime.

**Mitigation:** Use configurable hard limits and collect rich information about a bounded candidate set rather than unlimited raw content.

## 33.5 Editorial quality is weaker than speech quality

**Risk:** The episode sounds polished but is not useful.

**Mitigation:** Keep editorial planning separate from script and audio generation so the user can inspect artifacts informally without adding an MVP metrics system.

## 33.6 Gemini preview instability

**Risk:** Voice drift, failed requests, or model replacement.

**Mitigation:** Short segments, retries, exact model logging, provider abstraction, and preserved transcripts.

## 33.7 Two-host format feels artificial

**Risk:** Reactions become repetitive or add no value.

**Mitigation:** Flexible symmetry, balanced word share, reaction warnings, and an eventual configurable single-host fallback. The fallback does not need to be implemented in MVP.

## 33.8 Source-grounding failure

**Risk:** Natural dialogue makes unsupported statements sound authoritative.

**Mitigation:** Claim IDs, claim-level supporting excerpts or primary-source locators, retrieval provenance, source-independence grouping, deterministic lineage checks, and explicit uncertainty.

## 33.9 Local feed availability

**Risk:** The phone cannot retrieve the feed when the host computer sleeps.

**Mitigation:** Document that the reference host must remain reachable during podcast refresh. Cloud publication is a later option if local availability proves inconvenient.

## 33.10 Prompt injection from research sources

**Risk:** A webpage tells the agent to alter its behavior or expose data.

**Mitigation:** Collection instructions explicitly classify source content as untrusted data; source text cannot authorize commands, tool use, credential access, or workflow changes.

## 33.11 Concurrent scheduled runs

**Risk:** Duplicate starts create conflicting run state, duplicate episodes, or lost RSS updates.

**Mitigation:** Claim one atomic, heartbeat-based lease per episode across the full agent workflow and hold one short-lived OS advisory lock per feed during feed read-modify-write. A duplicate episode start exits as a no-op, while abandoned leases are recoverable and unrelated episodes may render concurrently.

---

# 34. Deferred roadmap

## V0.2

Potential improvements based on observed failures:

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
3. One capability-aware collection phase with native Codex research as the public-web fallback.
4. One world/U.S./Seattle news example profile.
5. One scheduled Codex workflow.
6. One Gemini multi-speaker renderer.
7. One private RSS feed.
8. One minimal per-run state file and human-readable result summary.

The core repository must remain free of topic-specific source integrations.

The world/U.S./Seattle profile exercises the generic engine as an example. Its news-specific sections, taxonomy, and collection preferences must remain profile data rather than becoming engine or skill constraints. The topic-generic evidence contract and profile schema preserve a clean path to future episode types without requiring those integrations to be built now.

This specification supersedes the earlier three-episode and two-episode MVP proposals.
