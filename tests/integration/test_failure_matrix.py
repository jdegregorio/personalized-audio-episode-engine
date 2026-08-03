from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]

# PRD section 30 is exercised across the focused tests named here. Keeping the
# map executable prevents a failure row from becoming an undocumented assumption
# without duplicating the already deterministic boundary tests.
FAILURE_MATRIX_EVIDENCE = {
    "Invalid profile": (
        "tests/unit/test_init_run_cli.py::"
        "test_init_run_cli_reports_invalid_profile_without_traceback"
    ),
    "Suggested collector skill absent": (
        "tests/unit/test_collection.py::"
        "test_collection_method_prefers_suitable_capability_and_falls_back"
    ),
    "Profile-required authenticated source absent": (
        "tests/unit/test_collection_cli.py::"
        "test_select_cli_terminalizes_missing_required_capability"
    ),
    "Specialized collection fails": (
        "tests/unit/test_collection_cli.py::"
        "test_select_cli_records_specialized_failure_and_native_fallback"
    ),
    "Dossier invalid": (
        "tests/unit/test_collection.py::test_second_invalid_dossier_terminalizes_and_releases_owner"
    ),
    "No qualifying content for an optional profile section": (
        "tests/integration/test_editorial_plans.py::"
        "test_optional_empty_section_golden_plan_avoids_filler"
    ),
    "Too few total credible candidates": (
        "tests/integration/test_editorial_plans.py::"
        "test_ordinary_and_shorter_golden_plans_are_valid"
    ),
    "Editorial plan invalid": (
        "tests/unit/test_editorial.py::test_second_invalid_plan_fails_and_releases_owner"
    ),
    "Script invalid": (
        "tests/unit/test_scriptwriting.py::test_second_invalid_script_fails_and_releases_owner"
    ),
    "One TTS segment fails": (
        "tests/integration/test_tts_rendering.py::"
        "test_transient_failure_uses_deterministic_backoff_without_repeating_prior_work"
    ),
    "TTS retries exhausted": (
        "tests/integration/test_tts_rendering.py::"
        "test_retry_exhaustion_preserves_completed_segment_and_resumes_only_failure"
    ),
    "MP3 validation fails": (
        "tests/integration/test_audio_assembly.py::"
        "test_invalid_final_format_never_becomes_publication_ready"
    ),
    "R2 asset upload or verification fails": (
        "tests/smoke/test_audio_assembly_workflow.py::"
        "test_documented_audio_and_offline_publication_create_a_resumable_podcast"
    ),
    "R2 conditional feed write conflicts": (
        "tests/smoke/test_audio_assembly_workflow.py::"
        "test_documented_audio_and_offline_publication_create_a_resumable_podcast"
    ),
    "Public R2 URL is unavailable or has wrong metadata": (
        "tests/unit/test_r2.py::test_r2_public_fetch_fails_closed_on_status_media_or_length"
    ),
    "Feed lock remains busy": (
        "tests/unit/test_leases.py::test_feed_lock_is_deterministic_bounded_and_mode_0600"
    ),
    "Retention and lifecycle configuration disagree": (
        "tests/unit/test_publication.py::"
        "test_rss_is_valid_idempotent_sorted_and_prunes_at_retention_boundary"
    ),
    "Same episode starts twice": (
        "tests/integration/test_run_concurrency.py::"
        "test_simultaneous_same_episode_has_one_owner_and_one_artifact_free_noop"
    ),
    "Different episodes publish together": (
        "tests/integration/test_publication_concurrency.py::"
        "test_two_hosts_conditionally_merge_different_episodes_without_lost_update"
    ),
}


@pytest.mark.integration
def test_every_prd_failure_row_has_stable_executable_evidence() -> None:
    assert len(FAILURE_MATRIX_EVIDENCE) == 19
    for node_id in FAILURE_MATRIX_EVIDENCE.values():
        relative_path, function_name = node_id.split("::", 1)
        path = ROOT / relative_path
        assert path.is_file(), node_id
        assert f"def {function_name}(" in path.read_text(encoding="utf-8"), node_id
