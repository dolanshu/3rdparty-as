"""Unit tests for the ADR-0006 configuration version repository.

The production repository is PostgreSQL (ADR-0006, ADR-0007). This test pins the
behaviour the PostgreSQL implementation must reproduce: versions are immutable,
numbered from one, and time always comes from the caller.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable

import pytest

from as_config_service.version_store import (
    ConfigVersion,
    InMemoryVersionStore,
    VersionStore,
)
from as_platform.api.contract import ConfigBundle, RuleDTO

pytestmark = pytest.mark.unit

BASE_TIME = 1_700_000_000.0


class RecordingClock:
    """A clock that counts how often it was asked for the time."""

    def __init__(self, value: float = BASE_TIME) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return self.value


def _bundle(version: str) -> ConfigBundle:
    """A one-rule bundle identified by ``version``."""
    return ConfigBundle(
        version=version,
        rules=(
            RuleDTO(rule_id="rule-755", prefix="+86755", action="translate", target="return-uas"),
        ),
    )


def _store(clock: Callable[[], float] | None = None) -> InMemoryVersionStore:
    """An empty store on an injected clock."""
    return InMemoryVersionStore(now=clock if clock is not None else RecordingClock())


def test_the_in_memory_store_satisfies_the_seam() -> None:
    """PostgreSQL replaces this implementation, so it must satisfy the Protocol."""
    store: VersionStore = _store()

    appended = store.append(_bundle("v1"), BASE_TIME)

    assert isinstance(appended, ConfigVersion)
    assert store.latest() is appended


def test_versions_are_numbered_from_one_and_increment() -> None:
    """The first append is version 1; every later append is one higher. ADR-0006."""
    store = _store()

    first = store.append(_bundle("v1"), BASE_TIME)
    second = store.append(_bundle("v2"), BASE_TIME + 1.0)
    third = store.append(_bundle("v3"), BASE_TIME + 2.0)

    assert (first.version, second.version, third.version) == (1, 2, 3)
    assert (first.created_at, second.created_at, third.created_at) == (
        BASE_TIME,
        BASE_TIME + 1.0,
        BASE_TIME + 2.0,
    )


def test_latest_is_the_last_appended_version_and_none_when_empty() -> None:
    """``latest()`` is the head of the immutable history."""
    store = _store()
    assert store.latest() is None

    first = store.append(_bundle("v1"), BASE_TIME)
    assert store.latest() is first

    second = store.append(_bundle("v2"), BASE_TIME + 1.0)
    assert store.latest() is second
    assert store.get(1) is first


def test_get_reads_history_and_returns_none_for_an_unknown_version() -> None:
    """An old version stays readable; a version that was never written is ``None``."""
    store = _store()
    first = store.append(_bundle("v1"), BASE_TIME)
    store.append(_bundle("v2"), BASE_TIME + 1.0)

    assert store.get(1) is first
    assert store.get(1) == first
    assert store.get(2) == store.latest()
    assert store.get(3) is None
    assert store.get(0) is None


def test_append_does_not_mutate_existing_versions() -> None:
    """A version row is immutable: appending changes nothing already written. ADR-0006."""
    store = _store()
    first = store.append(_bundle("v1"), BASE_TIME)
    first_bundle = first.bundle
    first_created_at = first.created_at

    second = store.append(_bundle("v2"), BASE_TIME + 1.0, change_id="co-1")

    assert first.bundle is first_bundle
    assert first.created_at == first_created_at
    assert first.bundle == _bundle("v1")
    assert first.version == 1
    assert second.version == 2
    assert second.change_id == "co-1"
    assert first.change_id is None


def test_history_keeps_append_order() -> None:
    """History is the append order, oldest first, and is a read-only view."""
    store = _store()
    first = store.append(_bundle("v1"), BASE_TIME)
    second = store.append(_bundle("v2"), BASE_TIME + 1.0)
    third = store.append(_bundle("v3"), BASE_TIME + 2.0)

    history = store.history()

    assert history == (first, second, third)
    assert tuple(version.version for version in history) == (1, 2, 3)
    assert tuple(version.bundle.version for version in history) == ("v1", "v2", "v3")


def test_version_carries_the_change_order_that_produced_it() -> None:
    """Every version row is traceable to the change order that wrote it. REQ-NF-10."""
    store = _store()

    assert store.append(_bundle("v1"), BASE_TIME).change_id is None
    assert store.append(_bundle("v2"), BASE_TIME + 1.0, change_id="co-7").change_id == "co-7"


def test_append_stamps_from_the_injected_clock_when_no_time_is_passed() -> None:
    """The constructor clock is the fallback, never the system clock."""
    clock = RecordingClock(BASE_TIME + 42.0)
    store = _store(clock)

    version = store.append(_bundle("v1"))

    assert version.created_at == BASE_TIME + 42.0
    assert clock.calls == 1


def test_store_reads_no_clock_and_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Time comes from the caller; the repository touches no clock and no socket. AGENT.md §5."""
    clock_reads: list[str] = []
    sockets: list[str] = []

    def fake_time() -> float:
        clock_reads.append("time")
        return 0.0

    def fake_monotonic() -> float:
        clock_reads.append("monotonic")
        return 0.0

    def fake_socket(*args: object, **kwargs: object) -> None:
        sockets.append("socket")

    monkeypatch.setattr(time, "time", fake_time)
    monkeypatch.setattr(time, "monotonic", fake_monotonic)
    monkeypatch.setattr(socket, "socket", fake_socket)

    store = _store(lambda: 0.0)
    store.append(_bundle("v1"), BASE_TIME)
    store.append(_bundle("v2"), BASE_TIME + 1.0)
    store.latest()
    store.get(1)
    store.history()

    assert clock_reads == []
    assert sockets == []
