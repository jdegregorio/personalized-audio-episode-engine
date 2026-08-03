from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from audio_engine.artifacts import EditorialPlan, EvidenceDossier, PublishedEpisode, RunState
from audio_engine.leases import LeaseManager
from audio_engine.lifecycle import RunWorkspace
from audio_engine.profile import load_profile
from audio_engine.publication import (
    MemoryObjectStore,
    PreconditionFailed,
    PublicationContext,
    PublicationError,
    merge_rss_feed,
    public_object_url,
    render_show_notes,
    validate_rss,
)

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "artifacts" / "valid"
PROFILE_PATH = ROOT / "examples" / "profiles" / "synthetic-marine-brief.yaml"


def _episode() -> PublishedEpisode:
    return PublishedEpisode.model_validate_json((FIXTURES / "published-episode.json").read_bytes())


def test_rss_is_valid_idempotent_sorted_and_prunes_at_retention_boundary() -> None:
    profile = load_profile(PROFILE_PATH, allowed_roots=[PROFILE_PATH.parent])
    episode = _episode()
    feed_url = "https://podcast.example.invalid/feeds/" + "t" * 43 + "/feed.xml"
    first = merge_rss_feed(
        None,
        profile=profile,
        episode=episode,
        feed_url=feed_url,
        retention_days=30,
    )
    rerun = merge_rss_feed(
        first,
        profile=profile,
        episode=episode,
        feed_url=feed_url,
        retention_days=30,
    )
    validate_rss(rerun, expected_guid=episode.guid)
    root = ET.fromstring(rerun)

    assert len(root.findall("channel/item")) == 1
    assert root.findtext("channel/item/guid") == "marine-feed:marine-brief:2026-01-15"
    enclosure = root.find("channel/item/enclosure")
    assert enclosure is not None
    assert enclosure.attrib["type"] == "audio/mpeg"
    assert enclosure.attrib["length"] == "4800000"
    assert root.findtext("channel/{http://www.itunes.com/dtds/podcast-1.0.dtd}duration") is None
    assert (
        root.findtext("channel/item/{http://www.itunes.com/dtds/podcast-1.0.dtd}duration") == "300"
    )

    old_data = episode.model_dump(mode="json")
    old_data.update(
        {
            "episode_date": "2025-12-16",
            "episode_key": "marine-brief:2025-12-16",
            "guid": "marine-feed:marine-brief:2025-12-16",
            "published_at": "2025-12-16T15:20:00Z",
            "title": "Expired synthetic episode",
        }
    )
    old = PublishedEpisode.model_validate(old_data)
    with_old = merge_rss_feed(
        None,
        profile=profile,
        episode=old,
        feed_url=feed_url,
        retention_days=30,
    )
    pruned = merge_rss_feed(
        with_old,
        profile=profile,
        episode=episode,
        feed_url=feed_url,
        retention_days=30,
    )
    assert ET.fromstring(pruned).findall("channel/item/guid")[0].text == episode.guid
    assert len(ET.fromstring(pruned).findall("channel/item")) == 1


def test_rss_rejects_duplicate_or_incomplete_items() -> None:
    profile = load_profile(PROFILE_PATH, allowed_roots=[PROFILE_PATH.parent])
    episode = _episode()
    feed = merge_rss_feed(
        None,
        profile=profile,
        episode=episode,
        feed_url="https://podcast.example.invalid/private/feed.xml",
        retention_days=30,
    )
    root = ET.fromstring(feed)
    channel = root.find("channel")
    assert channel is not None
    item = channel.find("item")
    assert item is not None
    channel.append(ET.fromstring(ET.tostring(item)))

    with pytest.raises(PublicationError, match="duplicate"):
        validate_rss(ET.tostring(root))

    item.find("enclosure").attrib["length"] = "not-a-number"  # type: ignore[union-attr]
    channel.remove(channel.findall("item")[1])
    with pytest.raises(PublicationError, match="numeric"):
        validate_rss(ET.tostring(root))


def test_show_notes_include_segments_grouped_sources_timestamps_and_disclosure(
    tmp_path: Path,
) -> None:
    profile = load_profile(PROFILE_PATH, allowed_roots=[PROFILE_PATH.parent])
    dossier = EvidenceDossier.model_validate_json((FIXTURES / "evidence-dossier.json").read_bytes())
    plan = EditorialPlan.model_validate_json((FIXTURES / "editorial-plan.json").read_bytes())
    state = RunState.model_validate_json((FIXTURES / "run-state.json").read_bytes())
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    context = PublicationContext(
        workspace=RunWorkspace(tmp_path, "Synthetic Marine Brief — 2026-01-15", state.episode_key),
        manager=LeaseManager(runtime, maximum_age=timedelta(hours=1)),
        profile=profile,
        state=state,
        dossier=dossier,
        plan=plan,
        transcript="Maya: Synthetic transcript.",
        final_audio=state.final_audio_validation,
    )

    transcript_url = "https://podcast.example.invalid/episodes/token/transcript.txt"
    notes = render_show_notes(
        context,
        generated_at=datetime(2026, 1, 15, 16, 0, tzinfo=UTC),
        transcript_url=transcript_url,
    )
    text = notes.decode()

    assert "Episode summary" in text
    assert "00:00" in text and "03:00" in text
    assert "Synthetic reef plot shows early habitat growth" in text
    assert "Sources" in text
    assert f'href="{transcript_url}"' in text
    assert "Open the plain-text transcript" in text
    assert "generated with AI" in text
    assert "Episode generation date" in text and "2026-01-15" in text
    assert "https://" in text


@pytest.mark.parametrize(
    ("base", "key"),
    [
        ("http://example.invalid", "episodes/token/file.mp3"),
        ("https://example.invalid/path", "episodes/token/file.mp3"),
        ("https://example.invalid", "../outside"),
        ("https://example.invalid", "/absolute"),
    ],
)
def test_public_url_rejects_ambiguous_or_unsafe_inputs(base: str, key: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        public_object_url(base, key)


def test_memory_store_enforces_create_and_replace_preconditions() -> None:
    store = MemoryObjectStore()
    body = b"feed"
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    etag = store.put(
        "feeds/token/feed.xml",
        body,
        content_type="application/rss+xml",
        cache_control="no-cache",
        sha256=digest,
        if_none_match=True,
    )

    with pytest.raises(PreconditionFailed):
        store.put(
            "feeds/token/feed.xml",
            body,
            content_type="application/rss+xml",
            cache_control="no-cache",
            sha256=digest,
            if_none_match=True,
        )
    with pytest.raises(PreconditionFailed):
        store.put(
            "feeds/token/feed.xml",
            body,
            content_type="application/rss+xml",
            cache_control="no-cache",
            sha256=digest,
            if_match='"stale"',
        )
    assert store.put(
        "feeds/token/feed.xml",
        body,
        content_type="application/rss+xml",
        cache_control="no-cache",
        sha256=digest,
        if_match=etag,
    )


def test_metadata_fixture_truthfully_omits_its_self_hash() -> None:
    episode = _episode()
    assets = {asset.kind: asset for asset in episode.assets}
    assert assets["audio"].sha256 is not None
    assert assets["episode_metadata"].sha256 is None
    assert (
        json.loads((FIXTURES / "published-episode.json").read_text())["assets"][3]["sha256"] is None
    )
