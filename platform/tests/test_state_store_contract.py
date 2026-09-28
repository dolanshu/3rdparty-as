"""Contract tests for StateStore: one set of cases, every implementation.

Acceptance: docs/acceptance/test-plan.md §5.2. The Redis implementation is
skipped when the client library is absent; the contract itself always exists.
See ADR-0002 (state externalised) and ADR-0007 (key namespace, TTL, idempotent
writes).
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from as_platform.state.in_memory import InMemoryStateStore
from as_platform.state.redis_store import RedisStateStore
from as_platform.state.store import StateStore, build_key

pytestmark = pytest.mark.contract

BINARY_VALUE = b"\x00\x01\xff\xfe\x7f\x80 body"


class FakeClock:
    """A clock the test advances by hand; no store may read the real one."""

    def __init__(self) -> None:
        self.now_value = 1_000.0

    def __call__(self) -> float:
        return self.now_value

    def advance(self, seconds: float) -> None:
        self.now_value += seconds


class FakeRedisClient:
    """In-process stand-in carrying the client surface the store uses."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    def set(self, key: str, value: bytes) -> None:
        self.values[key] = value

    def setex(self, key: str, ttl_seconds: int, value: bytes) -> None:
        self.values[key] = value
        self.ttls[key] = ttl_seconds

    def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.ttls.pop(key, None)

    def expire(self, key: str, ttl_seconds: int) -> None:
        self.ttls[key] = ttl_seconds


def _make_in_memory(clock: FakeClock) -> StateStore:
    return InMemoryStateStore(now=clock)


def _make_redis(clock: FakeClock) -> StateStore:
    pytest.importorskip("redis")  # the production client library
    return RedisStateStore(client=FakeRedisClient(), now=clock)


FACTORIES: dict[str, Callable[[FakeClock], StateStore]] = {
    "in_memory": _make_in_memory,
    "redis": _make_redis,
}


@pytest.fixture(params=sorted(FACTORIES))
def make_store(request: pytest.FixtureRequest) -> Callable[[FakeClock], StateStore]:
    """A factory for each implementation under contract."""
    return FACTORIES[request.param]


def test_get_of_a_missing_key_returns_none(make_store: Callable[[FakeClock], StateStore]) -> None:
    """A miss is None, never an exception. Case 1."""
    store = make_store(FakeClock())

    assert store.get("as:translation:dialog:missing") is None


def test_get_returns_the_value_byte_for_byte(make_store: Callable[[FakeClock], StateStore]) -> None:
    """Values are binary safe. Case 2."""
    store = make_store(FakeClock())

    store.set("as:translation:dialog:call-1", BINARY_VALUE, ttl_seconds=30.0)

    assert store.get("as:translation:dialog:call-1") == BINARY_VALUE


def test_writing_the_same_value_twice_is_idempotent(
    make_store: Callable[[FakeClock], StateStore],
) -> None:
    """A repeated write leaves the same result. Case 3."""
    store = make_store(FakeClock())

    store.set("as:translation:dialog:call-1", BINARY_VALUE, ttl_seconds=30.0)
    store.set("as:translation:dialog:call-1", BINARY_VALUE, ttl_seconds=30.0)

    assert store.get("as:translation:dialog:call-1") == BINARY_VALUE


def test_value_is_gone_once_the_ttl_passes(make_store: Callable[[FakeClock], StateStore]) -> None:
    """Expiry is decided by the injected clock. Case 4."""
    clock = FakeClock()
    store = make_store(clock)

    store.set("as:translation:dialog:call-1", BINARY_VALUE, ttl_seconds=1.0)
    assert store.get("as:translation:dialog:call-1") == BINARY_VALUE

    clock.advance(1.5)

    assert store.get("as:translation:dialog:call-1") is None


def test_expire_shortens_the_lifetime_of_a_key(
    make_store: Callable[[FakeClock], StateStore],
) -> None:
    """expire() re-arms the TTL from the injected clock."""
    clock = FakeClock()
    store = make_store(clock)

    store.set("as:translation:dialog:call-1", BINARY_VALUE, ttl_seconds=60.0)
    store.expire("as:translation:dialog:call-1", ttl_seconds=1.0)
    clock.advance(2.0)

    assert store.get("as:translation:dialog:call-1") is None


def test_delete_is_idempotent(make_store: Callable[[FakeClock], StateStore]) -> None:
    """Deleting twice is not an error. Case 5."""
    store = make_store(FakeClock())
    store.set("as:translation:dialog:call-1", BINARY_VALUE, ttl_seconds=30.0)

    store.delete("as:translation:dialog:call-1")
    assert store.get("as:translation:dialog:call-1") is None

    store.delete("as:translation:dialog:call-1")
    assert store.get("as:translation:dialog:call-1") is None


def test_key_namespace_is_case_kind_id(make_store: Callable[[FakeClock], StateStore]) -> None:
    """Keys are built as as:{case}:{kind}:{id}. Case 6, ADR-0007."""
    store = make_store(FakeClock())

    key = store.build_key("translation", "dialog", "call-1")

    assert key == "as:translation:dialog:call-1"
    assert key == build_key("translation", "dialog", "call-1")


def test_write_order_does_not_change_the_final_state(
    make_store: Callable[[FakeClock], StateStore],
) -> None:
    """Replaying writes in another order yields the same state. Case 7."""
    forward = make_store(FakeClock())
    backward = make_store(FakeClock())

    for key, value in (("as:a:dialog:1", b"first"), ("as:a:dialog:2", b"second")):
        forward.set(key, value, ttl_seconds=30.0)
    for key, value in (("as:a:dialog:2", b"second"), ("as:a:dialog:1", b"first")):
        backward.set(key, value, ttl_seconds=30.0)

    assert forward.get("as:a:dialog:1") == backward.get("as:a:dialog:1")
    assert forward.get("as:a:dialog:2") == backward.get("as:a:dialog:2")


def test_no_implementation_reads_the_system_clock(
    make_store: Callable[[FakeClock], StateStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Time comes from the injected clock, never from time.time()."""
    reads: list[str] = []

    def fake_time() -> float:
        reads.append("time")
        return 0.0

    def fake_monotonic() -> float:
        reads.append("monotonic")
        return 0.0

    monkeypatch.setattr(time, "time", fake_time)
    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    store = make_store(FakeClock())
    store.set("as:translation:dialog:call-1", BINARY_VALUE, ttl_seconds=30.0)
    store.get("as:translation:dialog:call-1")
    store.expire("as:translation:dialog:call-1", ttl_seconds=5.0)
    store.delete("as:translation:dialog:call-1")

    assert reads == []
