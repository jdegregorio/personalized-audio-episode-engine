from __future__ import annotations

import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from audio_engine.artifacts import PublishedEpisode
from audio_engine.profile import load_profile
from audio_engine.publication import MemoryObjectStore, StoredObject, write_feed_revision

ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "artifacts" / "valid" / "published-episode.json"
PROFILE_PATH = ROOT / "examples" / "profiles" / "synthetic-marine-brief.yaml"


class _SimultaneousInitialReadStore(MemoryObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self._initial_reads = threading.Barrier(2)
        self._read_count = 0
        self._read_lock = threading.Lock()

    def get(self, key: str) -> StoredObject | None:
        value = super().get(key)
        with self._read_lock:
            self._read_count += 1
            should_wait = self._read_count <= 2
        if should_wait:
            self._initial_reads.wait(timeout=5)
        return value


def _episode(profile_id: str, episode_date: str) -> PublishedEpisode:
    episode = PublishedEpisode.model_validate_json(FIXTURE.read_bytes())
    data = episode.model_dump(mode="json")
    data.update(
        {
            "episode_key": f"{profile_id}:{episode_date}",
            "profile_id": profile_id,
            "episode_date": episode_date,
            "guid": f"marine-brief:{profile_id}:{episode_date}",
            "title": f"Synthetic {profile_id} {episode_date}",
        }
    )
    return PublishedEpisode.model_validate(data)


@pytest.mark.integration
def test_two_hosts_conditionally_merge_different_episodes_without_lost_update() -> None:
    profile = load_profile(PROFILE_PATH, allowed_roots=[PROFILE_PATH.parent])
    store = _SimultaneousInitialReadStore()
    feed_key = "feeds/" + "t" * 43 + "/feed.xml"
    feed_url = "https://podcast.example.invalid/" + feed_key
    episodes = (_episode("marine-brief", "2026-01-15"), _episode("second-brief", "2026-01-16"))

    def publish(episode: PublishedEpisode) -> bool:
        return write_feed_revision(
            store,
            feed_key=feed_key,
            profile=profile,
            episode=episode,
            feed_url=feed_url,
            retention_days=30,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, episodes))

    feed = store.get(feed_key)
    assert feed is not None
    guids = [node.text for node in ET.fromstring(feed.body).findall("channel/item/guid")]
    assert results == [True, True]
    assert set(guids) == {episode.guid for episode in episodes}
    assert len(guids) == 2
