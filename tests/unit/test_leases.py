from __future__ import annotations

import fcntl
import json
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, current_thread

import pytest

from audio_engine.leases import LeaseAcquisition, LeaseError, LeaseManager, LeaseRecord
from audio_engine.storage import atomic_write_json

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "artifacts" / "valid"


def _clock(current: list[datetime]) -> datetime:
    return current[0]


def test_lease_acquire_noop_refresh_and_owner_only_release(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    current = [datetime(2026, 1, 15, 15, 0, tzinfo=UTC)]
    manager = LeaseManager(
        runtime,
        maximum_age=timedelta(hours=1),
        clock=lambda: _clock(current),
    )

    acquired = manager.acquire("synthetic-lifecycle:2026-01-15", "run_owner")
    no_op = manager.acquire("synthetic-lifecycle:2026-01-15", "run_other")
    current[0] += timedelta(minutes=5)
    refreshed = manager.refresh("synthetic-lifecycle:2026-01-15", "run_owner")

    assert acquired.acquired
    assert not no_op.acquired
    assert no_op.lease.run_id == "run_owner"
    assert refreshed.last_heartbeat_at == current[0]
    assert manager.lease_path(acquired.lease.episode_key).stat().st_mode & 0o777 == 0o600

    with pytest.raises(LeaseError, match="another run"):
        manager.refresh(acquired.lease.episode_key, "run_other")
    with pytest.raises(LeaseError, match="another run"):
        manager.release(acquired.lease.episode_key, "run_other")

    manager.release(acquired.lease.episode_key, "run_owner")
    assert not manager.lease_path(acquired.lease.episode_key).exists()


def test_contender_retries_lease_visible_before_creator_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    manager = LeaseManager(runtime, maximum_age=timedelta(minutes=1))
    episode_key = "synthetic-lifecycle:2026-01-15"
    creator_waiting = Event()
    release_creator = Event()
    observer_locked = Event()
    release_observer = Event()
    observer_retries = 0
    real_flock = fcntl.flock
    real_sleep = time.sleep

    def controlled_flock(descriptor: int, operation: int) -> None:
        thread_name = current_thread().name
        if thread_name.startswith("lease-creator") and not creator_waiting.is_set():
            creator_waiting.set()
            assert release_creator.wait(timeout=5)
        real_flock(descriptor, operation)
        if thread_name.startswith("lease-observer") and not observer_locked.is_set():
            observer_locked.set()
            assert release_observer.wait(timeout=5)

    def controlled_sleep(delay: float) -> None:
        nonlocal observer_retries
        if current_thread().name.startswith("lease-observer"):
            observer_retries += 1
            if observer_retries == 3:
                release_creator.set()
        real_sleep(delay)

    monkeypatch.setattr("audio_engine.leases.fcntl.flock", controlled_flock)
    monkeypatch.setattr("audio_engine.leases.time.sleep", controlled_sleep)
    with (
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="lease-creator") as creators,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="lease-observer") as observers,
    ):
        creator = creators.submit(manager.acquire, episode_key, "run_creator")
        assert creator_waiting.wait(timeout=5)
        observer = observers.submit(manager.acquire, episode_key, "run_observer")
        assert observer_locked.wait(timeout=5)
        release_observer.set()
        try:
            created = creator.result(timeout=5)
            observed = observer.result(timeout=5)
        finally:
            release_creator.set()
            release_observer.set()

    assert created.acquired
    assert not observed.acquired
    assert observed.lease.run_id == "run_creator"
    assert observer_retries >= 3


def test_stale_lease_is_quarantined_before_new_owner(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    current = [datetime(2026, 1, 15, 15, 0, tzinfo=UTC)]
    manager = LeaseManager(
        runtime,
        maximum_age=timedelta(minutes=30),
        clock=lambda: _clock(current),
    )
    episode_key = "synthetic-lifecycle:2026-01-15"
    manager.acquire(episode_key, "run_abandoned")

    current[0] += timedelta(minutes=31)
    recovered = manager.acquire(episode_key, "run_recovery")

    assert recovered.acquired
    assert recovered.recovered
    assert recovered.lease.run_id == "run_recovery"
    quarantined = list((runtime / "locks").glob("episode-*.stale-*.json"))
    assert len(quarantined) == 1
    stale = LeaseRecord.model_validate_json(quarantined[0].read_bytes())
    assert stale.run_id == "run_abandoned"


def test_live_lease_cannot_be_recovered_at_exact_expiry(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    current = [datetime(2026, 1, 15, 15, 0, tzinfo=UTC)]
    manager = LeaseManager(
        runtime,
        maximum_age=timedelta(minutes=30),
        clock=lambda: _clock(current),
    )
    episode_key = "synthetic-lifecycle:2026-01-15"
    manager.acquire(episode_key, "run_owner")

    current[0] += timedelta(minutes=30)
    result = manager.acquire(episode_key, "run_other")

    assert not result.acquired
    assert result.lease.run_id == "run_owner"
    assert not list((runtime / "locks").glob("episode-*.stale-*.json"))


def test_terminal_owner_can_be_recovered_without_waiting_for_age(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    now = datetime(2026, 1, 15, 15, 0, tzinfo=UTC)
    manager = LeaseManager(runtime, maximum_age=timedelta(hours=6), clock=lambda: now)
    episode_key = "synthetic-lifecycle:2026-01-15"
    run_id = "run_terminal"
    manager.acquire(episode_key, run_id)
    state_data = json.loads((FIXTURE_ROOT / "run-state.json").read_text(encoding="utf-8"))
    state_data["run_id"] = run_id
    state_data["episode_key"] = episode_key
    state_data["profile_id"] = "synthetic-lifecycle"
    state_path = runtime / "runs" / "2026-01-15" / "synthetic-lifecycle" / run_id / "state.json"
    state_path.parent.mkdir(parents=True)
    atomic_write_json(state_path, state_data)

    recovered = manager.acquire(episode_key, "run_after_terminal")

    assert recovered.acquired
    assert recovered.recovered
    assert recovered.lease.run_id == "run_after_terminal"


def test_corrupt_lease_fails_closed_without_quarantine(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    manager = LeaseManager(runtime, maximum_age=timedelta(minutes=1))
    episode_key = "synthetic-lifecycle:2026-01-15"
    path = manager.lease_path(episode_key)
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(LeaseError, match="unreadable or invalid"):
        manager.acquire(episode_key, "run_new")

    assert path.exists()
    assert not list(path.parent.glob("episode-*.stale-*.json"))


def test_persistently_empty_lease_fails_closed_without_quarantine(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    manager = LeaseManager(runtime, maximum_age=timedelta(minutes=1))
    episode_key = "synthetic-lifecycle:2026-01-15"
    path = manager.lease_path(episode_key)
    path.parent.mkdir(parents=True)
    path.touch(mode=0o600)

    with pytest.raises(LeaseError, match="did not converge"):
        manager.acquire(episode_key, "run_new")

    assert path.exists()
    assert not list(path.parent.glob("episode-*.stale-*.json"))


def test_naive_lease_clock_is_rejected(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    manager = LeaseManager(
        runtime,
        maximum_age=timedelta(minutes=1),
        clock=lambda: datetime(2026, 1, 15, 15, 0),
    )

    with pytest.raises(LeaseError, match="timezone-aware"):
        manager.acquire("synthetic-lifecycle:2026-01-15", "run_owner")


def test_refresh_rejects_clock_rollback_without_changing_heartbeat(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    current = [datetime(2026, 1, 15, 15, 0, tzinfo=UTC)]
    manager = LeaseManager(
        runtime,
        maximum_age=timedelta(minutes=30),
        clock=lambda: _clock(current),
    )
    episode_key = "synthetic-lifecycle:2026-01-15"
    acquired = manager.acquire(episode_key, "run_owner")
    current[0] -= timedelta(seconds=1)

    with pytest.raises(LeaseError, match="precedes"):
        manager.refresh(episode_key, "run_owner")

    persisted = LeaseRecord.model_validate_json(manager.lease_path(episode_key).read_bytes())
    assert persisted.last_heartbeat_at == acquired.lease.last_heartbeat_at


def test_mutation_fences_stale_takeover_until_write_finishes(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    current = [datetime(2026, 1, 15, 15, 0, tzinfo=UTC)]
    manager = LeaseManager(
        runtime,
        maximum_age=timedelta(minutes=1),
        clock=lambda: _clock(current),
    )
    episode_key = "synthetic-lifecycle:2026-01-15"
    manager.acquire(episode_key, "run_owner")
    mutation_started = Event()
    allow_finish = Event()
    contender_started = Event()

    def hold_mutation() -> None:
        with manager.mutation(episode_key, "run_owner"):
            current[0] += timedelta(minutes=2)
            mutation_started.set()
            assert allow_finish.wait(timeout=5)

    def contend() -> LeaseAcquisition:
        contender_started.set()
        return manager.acquire(episode_key, "run_contender")

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(hold_mutation)
        assert mutation_started.wait(timeout=5)
        contender = executor.submit(contend)
        assert contender_started.wait(timeout=5)
        try:
            with pytest.raises(FutureTimeoutError):
                contender.result(timeout=0.2)
        finally:
            allow_finish.set()
        owner.result(timeout=5)
        result = contender.result(timeout=5)

    assert not result.acquired
    assert result.lease.run_id == "run_owner"
    persisted = LeaseRecord.model_validate_json(manager.lease_path(episode_key).read_bytes())
    assert persisted.last_heartbeat_at == current[0]
