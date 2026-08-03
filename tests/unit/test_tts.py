from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from audio_engine.artifacts import ArtifactReference, EditorialPlan, EpisodeScript
from audio_engine.profile import EpisodeProfile, load_profile
from audio_engine.storage import sha256_file
from audio_engine.tts import (
    SpeechRendererCapabilities,
    TtsPreparationError,
    build_tts_preparation,
    estimate_input_tokens,
    renderer_capabilities,
    renderer_input,
)
from audio_engine.validation import load_artifact_file, render_transcript

ROOT = Path(__file__).parents[2]
ARTIFACT_ROOT = ROOT / "tests" / "fixtures" / "artifacts" / "valid"
FIXED_NOW = datetime(2026, 1, 15, 15, 15, tzinfo=UTC)


def _inputs() -> tuple[EpisodeScript, EditorialPlan, EpisodeProfile, ArtifactReference]:
    script_path = ARTIFACT_ROOT / "episode-script.json"
    script, script_report = load_artifact_file("script", script_path)
    plan, plan_report = load_artifact_file("plan", ARTIFACT_ROOT / "editorial-plan.json")
    profile_path = ROOT / "examples" / "profiles" / "synthetic-marine-brief.yaml"
    profile = load_profile(profile_path, allowed_roots=[profile_path.parent])
    assert isinstance(script, EpisodeScript), script_report.errors
    assert isinstance(plan, EditorialPlan), plan_report.errors
    return (
        script,
        plan,
        profile,
        ArtifactReference(
            artifact_type="script",
            path="episode-script.json",
            sha256=sha256_file(script_path),
        ),
    )


def _build(
    script: EpisodeScript,
    plan: EditorialPlan,
    profile: EpisodeProfile,
    script_reference: ArtifactReference,
    *,
    capabilities: SpeechRendererCapabilities | None = None,
):
    return build_tts_preparation(
        script,
        plan,
        profile,
        episode_script=script_reference,
        transcript=script.transcript,
        created_at=FIXED_NOW,
        capabilities=capabilities,
    )


def _expanded_script(
    script: EpisodeScript,
    profile: EpisodeProfile,
    *,
    safe_tokens: int,
    extra_turns: int,
    words_per_turn: int,
) -> tuple[EpisodeScript, EpisodeProfile]:
    data = script.model_dump(mode="json")
    turns = cast(list[dict[str, Any]], data["turns"])
    template = copy.deepcopy(turns[2])
    additions: list[dict[str, Any]] = []
    for index in range(extra_turns):
        addition = copy.deepcopy(template)
        addition["turn_id"] = f"turn_extra_{index:03d}"
        addition["speaker"] = "Maya" if index % 2 == 0 else "Daniel"
        addition["text"] = " ".join(["context"] * words_per_turn)
        additions.append(addition)
    data["turns"] = [*turns[:3], *additions, *turns[3:]]
    first_segment = cast(list[dict[str, Any]], data["segments"])[0]
    first_segment["turn_ids"] = [
        "turn_intro",
        "turn_reef_fact",
        "turn_reef_analysis",
        *[addition["turn_id"] for addition in additions],
    ]
    data["safe_input_tokens"] = safe_tokens
    for segment in cast(list[dict[str, Any]], data["segments"]):
        segment["estimated_input_tokens"] = min(100, safe_tokens)
    profile_data = profile.model_dump(mode="json")
    cast(dict[str, Any], profile_data["tts"])["safe_input_tokens"] = safe_tokens
    return EpisodeScript.model_validate(data), EpisodeProfile.model_validate(profile_data)


def test_estimate_input_tokens_is_deterministic_and_utf8_bounded() -> None:
    assert estimate_input_tokens("") == 1
    assert estimate_input_tokens("abc") == 1
    assert estimate_input_tokens("abcd") == 2
    assert estimate_input_tokens("éé") == 2


def test_known_gemini_capabilities_are_explicit() -> None:
    capabilities = renderer_capabilities("gemini", "gemini-3.1-flash-tts-preview")

    assert capabilities.absolute_input_tokens == 8_192
    assert capabilities.maximum_speakers == 2


def test_unknown_renderer_model_fails_closed() -> None:
    with pytest.raises(TtsPreparationError, match="no capability record"):
        renderer_capabilities("gemini", "future-model")


def test_build_preparation_preserves_transcript_hosts_and_natural_boundaries() -> None:
    script, plan, profile, reference = _inputs()

    manifest, prompts = _build(script, plan, profile, reference)

    assert len(prompts) == 2
    assert [segment.turn_ids for segment in manifest.segments] == [
        ["turn_intro", "turn_reef_fact", "turn_reef_analysis"],
        ["turn_transition", "turn_sensor_fact", "turn_outro"],
    ]
    assert "".join(prompt.transcript for prompt in prompts) == render_transcript(script)
    assert all(prompt.hosts == manifest.hosts for prompt in prompts)
    assert all(prompt.scene_description == manifest.scene_description for prompt in prompts)
    assert [(host.name, host.voice) for host in manifest.hosts] == [
        (speaker.name, speaker.voice) for speaker in script.speakers
    ]
    assert prompts[0].continuity_context is None
    assert prompts[1].continuity_context is not None
    assert "turn_transition" in prompts[1].turn_ids
    assert all(prompt.estimated_input_tokens <= manifest.safe_input_tokens for prompt in prompts)


def test_provider_instructions_do_not_leak_into_exact_transcript() -> None:
    script, plan, profile, reference = _inputs()
    _, prompts = _build(script, plan, profile, reference)

    for prompt in prompts:
        assert prompt.scene_description not in prompt.transcript
        assert all(note not in prompt.transcript for note in prompt.director_notes)
        if prompt.continuity_context:
            assert prompt.continuity_context not in prompt.transcript
        payload = json.loads(renderer_input(prompt))
        assert payload["transcript"] == prompt.transcript
        assert "sha256" not in renderer_input(prompt)


def test_prompt_rejects_a_transcript_speaker_name_mismatch() -> None:
    script, plan, profile, reference = _inputs()
    _, prompts = _build(script, plan, profile, reference)
    data = prompts[0].model_dump(mode="json")
    data["transcript"] = cast(str, data["transcript"]).replace("Maya: ", "Unknown: ", 1)

    with pytest.raises(ValidationError, match="speaker names must exactly match"):
        type(prompts[0]).model_validate(data)


def test_oversized_discussion_splits_only_as_needed_and_stays_bounded() -> None:
    script, plan, profile, reference = _inputs()
    expanded, constrained_profile = _expanded_script(
        script,
        profile,
        safe_tokens=500,
        extra_turns=12,
        words_per_turn=35,
    )
    capabilities = SpeechRendererCapabilities(
        provider=constrained_profile.tts.provider,
        model=constrained_profile.tts.model,
        absolute_input_tokens=8_192,
        maximum_speakers=2,
    )

    manifest, prompts = _build(
        expanded,
        plan,
        constrained_profile,
        reference,
        capabilities=capabilities,
    )

    reef_segments = [
        segment for segment in manifest.segments if "segment_reef" in segment.planned_segment_ids
    ]
    assert len(reef_segments) > 1
    assert all(prompt.estimated_input_tokens <= 500 for prompt in prompts)
    assert [turn_id for segment in manifest.segments for turn_id in segment.turn_ids] == [
        turn.turn_id for turn in expanded.turns
    ]
    assert "".join(prompt.transcript for prompt in prompts) == render_transcript(expanded)


@pytest.mark.parametrize("safe_tokens", [400, 500, 700, 1_000, 7_000])
def test_every_emitted_segment_respects_configured_boundary(safe_tokens: int) -> None:
    script, plan, profile, reference = _inputs()
    expanded, constrained_profile = _expanded_script(
        script,
        profile,
        safe_tokens=safe_tokens,
        extra_turns=16,
        words_per_turn=18,
    )
    capabilities = SpeechRendererCapabilities(
        provider=constrained_profile.tts.provider,
        model=constrained_profile.tts.model,
        absolute_input_tokens=8_192,
        maximum_speakers=2,
    )

    _, prompts = _build(
        expanded,
        plan,
        constrained_profile,
        reference,
        capabilities=capabilities,
    )

    assert max(prompt.estimated_input_tokens for prompt in prompts) <= safe_tokens


def test_one_oversized_spoken_turn_fails_instead_of_splitting_text() -> None:
    script, plan, profile, reference = _inputs()
    expanded, constrained_profile = _expanded_script(
        script,
        profile,
        safe_tokens=400,
        extra_turns=1,
        words_per_turn=1_000,
    )
    capabilities = SpeechRendererCapabilities(
        provider=constrained_profile.tts.provider,
        model=constrained_profile.tts.model,
        absolute_input_tokens=8_192,
        maximum_speakers=2,
    )

    with pytest.raises(TtsPreparationError, match="one spoken turn exceeds"):
        _build(
            expanded,
            plan,
            constrained_profile,
            reference,
            capabilities=capabilities,
        )


def test_safe_limit_cannot_exceed_model_absolute_limit() -> None:
    script, plan, profile, reference = _inputs()
    capabilities = SpeechRendererCapabilities(
        provider=profile.tts.provider,
        model=profile.tts.model,
        absolute_input_tokens=6_999,
        maximum_speakers=2,
    )

    with pytest.raises(TtsPreparationError, match="exceeds the model absolute"):
        _build(script, plan, profile, reference, capabilities=capabilities)


@pytest.mark.parametrize(
    ("provider", "model", "speakers", "message"),
    [
        ("other", "gemini-3.1-flash-tts-preview", 2, "do not match"),
        ("gemini", "other-model", 2, "do not match"),
        ("gemini", "gemini-3.1-flash-tts-preview", 1, "does not support"),
    ],
)
def test_capability_mismatch_fails_closed(
    provider: str,
    model: str,
    speakers: int,
    message: str,
) -> None:
    script, plan, profile, reference = _inputs()
    capabilities = SpeechRendererCapabilities(provider, model, 8_192, speakers)

    with pytest.raises(TtsPreparationError, match=message):
        _build(script, plan, profile, reference, capabilities=capabilities)


def test_script_speaker_voice_mismatch_fails() -> None:
    script, plan, profile, reference = _inputs()
    data = script.model_dump(mode="json")
    cast(list[dict[str, Any]], data["speakers"])[0]["voice"] = "different-voice"
    mismatched = EpisodeScript.model_validate(data)

    with pytest.raises(TtsPreparationError, match="do not match"):
        _build(mismatched, plan, profile, reference)


def test_valid_reversed_script_speaker_order_is_preserved() -> None:
    script, plan, profile, reference = _inputs()
    data = script.model_dump(mode="json")
    cast(list[dict[str, Any]], data["speakers"]).reverse()
    reversed_script = EpisodeScript.model_validate(data)

    manifest, prompts = _build(reversed_script, plan, profile, reference)

    assert [host.name for host in manifest.hosts] == ["Daniel", "Maya"]
    assert all(prompt.hosts == manifest.hosts for prompt in prompts)


def test_naive_preparation_timestamp_is_rejected() -> None:
    script, plan, profile, reference = _inputs()

    with pytest.raises(TtsPreparationError, match="timezone-aware"):
        build_tts_preparation(
            script,
            plan,
            profile,
            episode_script=reference,
            transcript=script.transcript,
            created_at=datetime(2026, 1, 15, 15, 15),
        )
