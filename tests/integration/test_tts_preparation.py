from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from audio_engine.artifacts import ArtifactReference, EditorialPlan, EpisodeScript, TtsManifest
from audio_engine.profile import load_profile
from audio_engine.storage import json_bytes, sha256_bytes, sha256_file
from audio_engine.tts import build_tts_preparation, renderer_input
from audio_engine.validation import load_artifact_file, render_transcript, validate_artifact_data

ROOT = Path(__file__).parents[2]
ARTIFACT_ROOT = ROOT / "tests" / "fixtures" / "artifacts" / "valid"


@pytest.mark.integration
def test_tts_manifest_and_prompt_references_form_one_exact_projection() -> None:
    script_path = ARTIFACT_ROOT / "episode-script.json"
    script, script_report = load_artifact_file("script", script_path)
    plan, plan_report = load_artifact_file("plan", ARTIFACT_ROOT / "editorial-plan.json")
    profile_path = ROOT / "examples" / "profiles" / "synthetic-marine-brief.yaml"
    profile = load_profile(profile_path, allowed_roots=[profile_path.parent])
    assert isinstance(script, EpisodeScript), script_report.errors
    assert isinstance(plan, EditorialPlan), plan_report.errors
    script_reference = ArtifactReference(
        artifact_type="script",
        path="episode-script.json",
        sha256=sha256_file(script_path),
    )

    manifest, prompts = build_tts_preparation(
        script,
        plan,
        profile,
        episode_script=script_reference,
        transcript=script.transcript,
        created_at=datetime(2026, 1, 15, 15, 15, tzinfo=UTC),
    )
    validated, report = validate_artifact_data("tts-manifest", manifest.model_dump(mode="json"))

    assert isinstance(validated, TtsManifest), report.errors
    assert [turn_id for segment in manifest.segments for turn_id in segment.turn_ids] == [
        turn.turn_id for turn in script.turns
    ]
    assert "".join(prompt.transcript for prompt in prompts) == render_transcript(script)
    for segment, prompt in zip(manifest.segments, prompts, strict=True):
        assert segment.prompt.sha256 == sha256_bytes(json_bytes(prompt.model_dump(mode="json")))
        assert segment.estimated_input_tokens == prompt.estimated_input_tokens
        assert prompt.estimated_input_tokens <= manifest.safe_input_tokens
        assert prompt.estimated_input_tokens <= manifest.absolute_input_tokens
        assert f"<TRANSCRIPT>\n{prompt.transcript}</TRANSCRIPT>" in renderer_input(prompt)
