"""Provider-neutral TTS request preparation and deterministic segmentation."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from audio_engine.artifacts import (
    ArtifactReference,
    EditorialPlan,
    EpisodeScript,
    RunState,
    ScriptTurn,
    TtsHost,
    TtsManifest,
    TtsManifestSegment,
    TtsSegmentPrompt,
)
from audio_engine.config import EngineSettings
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import (
    LifecycleError,
    RunWorkspace,
    load_run_state,
    record_tts_preparation,
)
from audio_engine.profile import EpisodeProfile
from audio_engine.safety import SafetyError, resolve_within_roots
from audio_engine.scriptwriting import open_script_run, record_script_attempt
from audio_engine.storage import StorageError, json_bytes, sha256_bytes, sha256_file
from audio_engine.validation import (
    load_artifact_file,
    render_transcript,
    validate_transcript_projection,
)

TTS_PROMPT_VERSION = "1.0.0"
_WORD = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_MINIMUM_TARGET_SECONDS = 2 * 60
_MAXIMUM_TARGET_SECONDS = 4 * 60


class TtsPreparationError(RuntimeError):
    """A safe TTS preparation or resume failure."""


@dataclass(frozen=True)
class SpeechRendererCapabilities:
    provider: str
    model: str
    absolute_input_tokens: int
    maximum_speakers: int

    def __post_init__(self) -> None:
        if self.absolute_input_tokens < 1 or self.maximum_speakers < 1:
            raise ValueError("speech renderer capabilities must use positive limits")


class SpeechRenderer(Protocol):
    """Provider-neutral boundary implemented by live renderers in their owning PR."""

    @property
    def capabilities(self) -> SpeechRendererCapabilities: ...

    def render(self, request: TtsSegmentPrompt) -> bytes: ...


_MODEL_CAPABILITIES = {
    ("gemini", "gemini-3.1-flash-tts-preview"): SpeechRendererCapabilities(
        provider="gemini",
        model="gemini-3.1-flash-tts-preview",
        absolute_input_tokens=8_192,
        maximum_speakers=2,
    )
}


@dataclass(frozen=True)
class TtsRunContext:
    workspace: RunWorkspace
    manager: LeaseManager
    run_id: str
    profile: EpisodeProfile
    state: RunState
    script: EpisodeScript
    plan: EditorialPlan
    transcript: str
    script_reference: ArtifactReference
    transcript_reference: ArtifactReference


@dataclass(frozen=True)
class TtsPreparationResult:
    status: Literal["prepared", "already_prepared"]
    manifest: TtsManifest

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": "tts/manifest.json",
            "maximum_estimated_input_tokens": max(
                segment.estimated_input_tokens for segment in self.manifest.segments
            ),
            "segment_count": len(self.manifest.segments),
            "status": self.status,
        }


@dataclass(frozen=True)
class _PromptContext:
    script: EpisodeScript
    profile: EpisodeProfile
    episode_script: ArtifactReference
    capabilities: SpeechRendererCapabilities
    scene: str
    notes: list[str]
    hosts: list[TtsHost]


def renderer_capabilities(provider: str, model: str) -> SpeechRendererCapabilities:
    """Return the explicit input/speaker limits for one configured renderer model."""
    capabilities = _MODEL_CAPABILITIES.get((provider, model))
    if capabilities is None:
        raise TtsPreparationError("configured speech provider/model has no capability record")
    return capabilities


def estimate_input_tokens(value: str) -> int:
    """Return a deterministic conservative UTF-8 token estimate."""
    return max(1, math.ceil(len(value.encode("utf-8")) / 3))


def renderer_input(prompt: TtsSegmentPrompt) -> str:
    """Serialize only structured provider input; local provenance remains out of band."""
    payload = {
        "continuity_context": prompt.continuity_context,
        "director_notes": prompt.director_notes,
        "hosts": [host.model_dump(mode="json") for host in prompt.hosts],
        "position": {
            "count": prompt.segment_count,
            "index": prompt.position,
        },
        "scene_description": prompt.scene_description,
        "transcript": prompt.transcript,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def open_tts_run(
    run_directory: Path,
    *,
    settings: EngineSettings,
    repo_root: Path,
) -> TtsRunContext:
    """Resolve a run whose accepted script and transcript are still authoritative."""
    script_context = open_script_run(run_directory, settings=settings, repo_root=repo_root)
    state = load_run_state(script_context.workspace.state_path)
    if state.script_validation is None or state.script_validation.status != "valid":
        raise TtsPreparationError("TTS preparation requires a valid script outcome")
    if state.current_stage != "tts":
        raise TtsPreparationError("TTS preparation can only run during the TTS stage")
    result = record_script_attempt(
        script_context.workspace,
        script_context.manager,
        script_context.run_id,
        profile=script_context.profile,
        candidate_path=script_context.workspace.run_directory / "episode-script.json",
        allowed_input_roots=script_context.allowed_input_roots,
        allowed_profile_roots=script_context.allowed_profile_roots,
    )
    if result.status != "already_valid":
        raise TtsPreparationError("TTS preparation requires a previously accepted script")
    state = load_run_state(script_context.workspace.state_path)
    script_reference = state.artifacts.get("episode_script")
    transcript_reference = state.artifacts.get("transcript")
    plan_reference = state.artifacts.get("editorial_plan")
    if script_reference is None or transcript_reference is None or plan_reference is None:
        raise TtsPreparationError("TTS preparation input references are incomplete")
    try:
        script_path = resolve_within_roots(
            script_context.workspace.run_directory / script_reference.path,
            [script_context.workspace.run_directory],
            must_exist=True,
        )
        transcript_path = resolve_within_roots(
            script_context.workspace.run_directory / transcript_reference.path,
            [script_context.workspace.run_directory],
            must_exist=True,
        )
        plan_path = resolve_within_roots(
            script_context.workspace.run_directory / plan_reference.path,
            [script_context.workspace.run_directory],
            must_exist=True,
        )
        if (
            sha256_file(script_path) != script_reference.sha256
            or sha256_file(transcript_path) != transcript_reference.sha256
            or sha256_file(plan_path) != plan_reference.sha256
        ):
            raise TtsPreparationError("TTS preparation input hash no longer matches its file")
        script_artifact, script_report = load_artifact_file("script", script_path)
        plan_artifact, plan_report = load_artifact_file("plan", plan_path)
        transcript = transcript_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, SafetyError, StorageError) as error:
        raise TtsPreparationError("TTS preparation input is missing or unsafe") from error
    if not isinstance(script_artifact, EpisodeScript) or not script_report.valid:
        raise TtsPreparationError("recorded episode script is invalid")
    if not isinstance(plan_artifact, EditorialPlan) or not plan_report.valid:
        raise TtsPreparationError("recorded editorial plan is invalid")
    if validate_transcript_projection(script_artifact, transcript):
        raise TtsPreparationError("recorded transcript no longer matches the script")
    return TtsRunContext(
        workspace=script_context.workspace,
        manager=script_context.manager,
        run_id=script_context.run_id,
        profile=script_context.profile,
        state=state,
        script=script_artifact,
        plan=plan_artifact,
        transcript=transcript,
        script_reference=script_reference,
        transcript_reference=transcript_reference,
    )


def prepare_tts(
    context: TtsRunContext,
    *,
    now: datetime | None = None,
    capabilities: SpeechRendererCapabilities | None = None,
) -> TtsPreparationResult:
    """Build and persist safe deterministic prompts, or verify an unchanged preparation."""
    selected_capabilities = capabilities or renderer_capabilities(
        context.profile.tts.provider, context.profile.tts.model
    )
    _validate_capabilities(context.profile, selected_capabilities)
    if context.state.tts_preparation is not None:
        manifest = _load_prepared_resume(context, selected_capabilities)
        return TtsPreparationResult("already_prepared", manifest)
    manifest, prompts = build_tts_preparation(
        context.script,
        context.plan,
        context.profile,
        episode_script=context.script_reference,
        transcript=context.transcript_reference,
        created_at=_aware_utc(now or datetime.now(UTC)),
        capabilities=selected_capabilities,
    )
    try:
        record_tts_preparation(
            context.workspace,
            context.manager,
            context.run_id,
            manifest=manifest,
            prompts=prompts,
        )
    except LifecycleError as error:
        raise TtsPreparationError(str(error)) from error
    return TtsPreparationResult("prepared", manifest)


def build_tts_preparation(
    script: EpisodeScript,
    plan: EditorialPlan,
    profile: EpisodeProfile,
    *,
    episode_script: ArtifactReference,
    transcript: ArtifactReference,
    created_at: datetime,
    capabilities: SpeechRendererCapabilities | None = None,
) -> tuple[TtsManifest, tuple[TtsSegmentPrompt, ...]]:
    """Build a manifest and prompts without writing files or calling a provider."""
    selected_capabilities = capabilities or renderer_capabilities(
        profile.tts.provider, profile.tts.model
    )
    _validate_capabilities(profile, selected_capabilities)
    if script.safe_input_tokens != profile.tts.safe_input_tokens:
        raise TtsPreparationError("script and profile safe input limits do not match")
    configured_hosts = {
        profile.hosts.female.name: profile.hosts.female,
        profile.hosts.male.name: profile.hosts.male,
    }
    if {speaker.name: speaker.voice for speaker in script.speakers} != {
        name: host.voice for name, host in configured_hosts.items()
    }:
        raise TtsPreparationError("script speakers do not match configured TTS hosts")
    expected_hosts = [
        TtsHost(
            name=speaker.name,
            voice=speaker.voice,
            description=configured_hosts[speaker.name].profile,
        )
        for speaker in script.speakers
    ]
    scene = _scene_description(profile)
    notes = _director_notes(profile)
    prompt_context = _PromptContext(
        script,
        profile,
        episode_script,
        selected_capabilities,
        scene,
        notes,
        expected_hosts,
    )
    natural_units = _natural_units(script, plan)
    fit_units = _split_oversized_units(natural_units, prompt_context)
    groups = _pack_units(fit_units, prompt_context)
    prompts: list[TtsSegmentPrompt] = []
    manifest_segments: list[TtsManifestSegment] = []
    total_words = sum(_turn_word_count(turn) for turn in script.turns)
    for index, turns in enumerate(groups, start=1):
        prompt = _make_prompt(
            turns,
            previous_turn=script.turns[script.turns.index(turns[0]) - 1]
            if turns[0] != script.turns[0]
            else None,
            position=index,
            segment_count=len(groups),
            context=prompt_context,
        )
        if prompt.estimated_input_tokens > profile.tts.safe_input_tokens:
            raise TtsPreparationError("prepared TTS segment exceeds the configured safe limit")
        prompt_path = f"tts/segment-{index:03d}.json"
        prompt_reference = ArtifactReference(
            artifact_type="tts-prompt",
            path=prompt_path,
            sha256=sha256_bytes(json_bytes(prompt.model_dump(mode="json"))),
        )
        planned_ids = list(
            dict.fromkeys(
                turn.planned_segment_id for turn in turns if turn.planned_segment_id is not None
            )
        )
        group_words = sum(_turn_word_count(turn) for turn in turns)
        duration = max(1, round(script.estimated_duration_seconds * group_words / total_words))
        prompts.append(prompt)
        manifest_segments.append(
            TtsManifestSegment(
                segment_id=prompt.segment_id,
                order=index,
                prompt=prompt_reference,
                turn_ids=[turn.turn_id for turn in turns],
                planned_segment_ids=planned_ids,
                estimated_duration_seconds=duration,
                estimated_input_tokens=prompt.estimated_input_tokens,
            )
        )
    if "".join(prompt.transcript for prompt in prompts) != render_transcript(script):
        raise TtsPreparationError("prepared TTS segments do not reconstruct the transcript")
    manifest = TtsManifest(
        contract_version="1.0",
        prompt_version=TTS_PROMPT_VERSION,
        created_at=_aware_utc(created_at),
        run_id=script.run_id,
        profile_id=script.profile_id,
        episode_date=script.episode_date,
        provider=selected_capabilities.provider,
        model=selected_capabilities.model,
        safe_input_tokens=profile.tts.safe_input_tokens,
        absolute_input_tokens=selected_capabilities.absolute_input_tokens,
        episode_script=episode_script,
        transcript=transcript,
        scene_description=scene,
        hosts=expected_hosts,
        segments=manifest_segments,
    )
    return manifest, tuple(prompts)


def _natural_units(script: EpisodeScript, plan: EditorialPlan) -> list[list[ScriptTurn]]:
    script_starts = {
        segment.turn_ids[0] for segment in sorted(script.segments, key=lambda item: item.order)[1:]
    }
    sections = {segment.segment_id: segment.section for segment in plan.segments}
    units: list[list[ScriptTurn]] = []
    current: list[ScriptTurn] = []
    for index, turn in enumerate(script.turns):
        previous = script.turns[index - 1] if index else None
        previous_section = (
            sections.get(previous.planned_segment_id)
            if previous is not None and previous.planned_segment_id is not None
            else None
        )
        current_section = (
            sections.get(turn.planned_segment_id) if turn.planned_segment_id is not None else None
        )
        natural_start = bool(
            current
            and (
                turn.turn_id in script_starts
                or turn.turn_type in {"transition", "outro"}
                or (
                    previous is not None
                    and previous.planned_segment_id is not None
                    and turn.planned_segment_id is not None
                    and previous.planned_segment_id != turn.planned_segment_id
                )
                or (
                    previous_section is not None
                    and current_section is not None
                    and previous_section != current_section
                )
            )
        )
        if natural_start:
            units.append(current)
            current = []
        current.append(turn)
    if current:
        units.append(current)
    return units


def _split_oversized_units(
    units: Sequence[Sequence[ScriptTurn]],
    context: _PromptContext,
) -> list[list[ScriptTurn]]:
    result: list[list[ScriptTurn]] = []
    turn_positions = {turn.turn_id: index for index, turn in enumerate(context.script.turns)}
    for unit in units:
        previous = (
            context.script.turns[turn_positions[unit[0].turn_id] - 1]
            if turn_positions[unit[0].turn_id]
            else None
        )
        if _fits(unit, previous, context):
            result.append(list(unit))
            continue
        current: list[ScriptTurn] = []
        for turn in unit:
            candidate = [*current, turn]
            candidate_previous = previous if not result else result[-1][-1]
            if current and not _fits(candidate, candidate_previous, context):
                result.append(current)
                current = [turn]
                candidate_previous = result[-1][-1]
                if not _fits(current, candidate_previous, context):
                    raise TtsPreparationError("one spoken turn exceeds the safe TTS input limit")
            else:
                current = candidate
        if current:
            result.append(current)
    return result


def _pack_units(
    units: Sequence[Sequence[ScriptTurn]],
    context: _PromptContext,
) -> list[list[ScriptTurn]]:
    groups: list[list[ScriptTurn]] = []
    current: list[ScriptTurn] = []
    target_seconds = context.profile.tts.target_segment_minutes * 60
    total_words = sum(_turn_word_count(turn) for turn in context.script.turns)

    def duration(turns: Sequence[ScriptTurn]) -> float:
        words = sum(_turn_word_count(turn) for turn in turns)
        return context.script.estimated_duration_seconds * words / total_words

    for unit in units:
        candidate = [*current, *unit]
        previous = groups[-1][-1] if groups else None
        should_close = bool(
            current
            and (
                duration(current) >= target_seconds
                or (
                    duration(candidate) > _MAXIMUM_TARGET_SECONDS
                    and duration(current) >= _MINIMUM_TARGET_SECONDS
                )
                or not _fits(candidate, previous, context)
            )
        )
        if should_close:
            groups.append(current)
            current = list(unit)
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


def _fits(
    turns: Sequence[ScriptTurn],
    previous_turn: ScriptTurn | None,
    context: _PromptContext,
) -> bool:
    prompt = _make_prompt(
        turns,
        previous_turn=previous_turn,
        position=10_000,
        segment_count=10_000,
        context=context,
    )
    return prompt.estimated_input_tokens <= min(
        context.profile.tts.safe_input_tokens, context.capabilities.absolute_input_tokens
    )


def _make_prompt(
    turns: Sequence[ScriptTurn],
    *,
    previous_turn: ScriptTurn | None,
    position: int,
    segment_count: int,
    context: _PromptContext,
) -> TtsSegmentPrompt:
    transcript = "".join(
        f"{turn.speaker}: "
        f"{'[' + turn.performance_cue + '] ' if turn.performance_cue else ''}"
        f"{turn.text}\n"
        for turn in turns
    )
    continuity = None
    if previous_turn is not None:
        prior_text = previous_turn.text[-300:]
        continuity = f"Previous segment ended with {previous_turn.speaker}: {prior_text}"
    prompt = TtsSegmentPrompt(
        contract_version="1.0",
        prompt_version=TTS_PROMPT_VERSION,
        provider=context.profile.tts.provider,
        model=context.profile.tts.model,
        episode_script=context.episode_script,
        segment_id=f"tts_segment_{position:03d}",
        position=position,
        segment_count=segment_count,
        scene_description=context.scene,
        director_notes=context.notes,
        hosts=context.hosts,
        continuity_context=continuity,
        transcript=transcript,
        turn_ids=[turn.turn_id for turn in turns],
        estimated_input_tokens=1,
    )
    data = prompt.model_dump(mode="json")
    data["estimated_input_tokens"] = estimate_input_tokens(renderer_input(prompt))
    return TtsSegmentPrompt.model_validate(data)


def _scene_description(profile: EpisodeProfile) -> str:
    style = profile.performance.style.replace("_", " ")
    pace = profile.performance.pace.replace("_", " ")
    audience = profile.audience.knowledge_level.replace("_", " ")
    return f"A {style} for an {audience} audience, delivered at a {pace} pace."


def _director_notes(profile: EpisodeProfile) -> list[str]:
    return [
        "Speak only the exact transcript; never read production metadata aloud.",
        f"Use audio performance cues {profile.performance.use_audio_tags}.",
        "Keep both recurring hosts natural, grounded, and consistent across segments.",
    ]


def _turn_word_count(turn: ScriptTurn) -> int:
    return max(1, len(_WORD.findall(turn.text)))


def _validate_capabilities(
    profile: EpisodeProfile,
    capabilities: SpeechRendererCapabilities,
) -> None:
    if profile.tts.provider != capabilities.provider or profile.tts.model != capabilities.model:
        raise TtsPreparationError("renderer capabilities do not match the configured model")
    if profile.tts.safe_input_tokens > capabilities.absolute_input_tokens:
        raise TtsPreparationError("configured safe input limit exceeds the model absolute limit")
    if capabilities.maximum_speakers < 2:
        raise TtsPreparationError("configured renderer does not support two speakers")


def _load_prepared_resume(
    context: TtsRunContext,
    capabilities: SpeechRendererCapabilities,
) -> TtsManifest:
    preparation = context.state.tts_preparation
    manifest_reference = context.state.artifacts.get("tts_manifest")
    if (
        preparation is None
        or manifest_reference is None
        or preparation.manifest != manifest_reference
        or preparation.episode_script != context.script_reference
        or preparation.transcript != context.transcript_reference
    ):
        raise TtsPreparationError("recorded TTS preparation state is incomplete")
    try:
        manifest_path = resolve_within_roots(
            context.workspace.run_directory / manifest_reference.path,
            [context.workspace.run_directory],
            must_exist=True,
        )
        if sha256_file(manifest_path) != manifest_reference.sha256:
            raise TtsPreparationError("recorded TTS manifest hash no longer matches its file")
        artifact, report = load_artifact_file("tts-manifest", manifest_path)
    except (SafetyError, StorageError) as error:
        raise TtsPreparationError("recorded TTS manifest is missing or unsafe") from error
    if not isinstance(artifact, TtsManifest) or not report.valid:
        raise TtsPreparationError("recorded TTS manifest is invalid")
    if (
        artifact.prompt_version != TTS_PROMPT_VERSION
        or artifact.run_id != context.run_id
        or artifact.profile_id != context.profile.id
        or artifact.episode_script != context.script_reference
        or artifact.transcript != context.transcript_reference
        or artifact.provider != capabilities.provider
        or artifact.model != capabilities.model
        or artifact.safe_input_tokens != context.profile.tts.safe_input_tokens
        or artifact.absolute_input_tokens != capabilities.absolute_input_tokens
        or preparation.segment_count != len(artifact.segments)
    ):
        raise TtsPreparationError("recorded TTS manifest provenance no longer matches state")
    prompts: list[TtsSegmentPrompt] = []
    try:
        for segment in artifact.segments:
            prompt_path = resolve_within_roots(
                context.workspace.run_directory / segment.prompt.path,
                [context.workspace.run_directory],
                must_exist=True,
            )
            if sha256_file(prompt_path) != segment.prompt.sha256:
                raise TtsPreparationError("recorded TTS prompt hash no longer matches its file")
            prompt = TtsSegmentPrompt.model_validate_json(prompt_path.read_text(encoding="utf-8"))
            if (
                prompt.segment_id != segment.segment_id
                or prompt.position != segment.order
                or prompt.segment_count != len(artifact.segments)
                or prompt.turn_ids != segment.turn_ids
                or prompt.hosts != artifact.hosts
                or prompt.scene_description != artifact.scene_description
                or prompt.estimated_input_tokens != segment.estimated_input_tokens
                or estimate_input_tokens(renderer_input(prompt)) != prompt.estimated_input_tokens
            ):
                raise TtsPreparationError("recorded TTS prompt no longer matches its manifest")
            prompts.append(prompt)
    except (OSError, UnicodeError, SafetyError, StorageError, ValueError) as error:
        raise TtsPreparationError("recorded TTS prompt is missing or invalid") from error
    if "".join(prompt.transcript for prompt in prompts) != context.transcript:
        raise TtsPreparationError("recorded TTS prompts no longer reconstruct the transcript")
    if [turn_id for segment in artifact.segments for turn_id in segment.turn_ids] != [
        turn.turn_id for turn in context.script.turns
    ]:
        raise TtsPreparationError("recorded TTS turn order no longer matches the script")
    return artifact


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TtsPreparationError("TTS preparation timestamps must be timezone-aware")
    return value.astimezone(UTC)
