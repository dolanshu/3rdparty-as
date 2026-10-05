"""Unit tests for Redis Sentinel client wiring on RedisStateStore."""

from __future__ import annotations

import time
from typing import Any

import pytest

from as_platform.state.redis_store import (
    RedisStateStore,
    _parse_sentinel_url,
    load_redis_store_from_env,
    parse_sentinel_hosts,
)

pytestmark = pytest.mark.unit


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


class FakeSentinel:
    """Records Sentinel construction and returns a fixed master client."""

    instances: list[FakeSentinel] = []

    def __init__(self, endpoints: list[tuple[str, int]], **kwargs: Any) -> None:
        self.endpoints = endpoints
        self.kwargs = kwargs
        self.master_client = FakeRedisClient()
        FakeSentinel.instances.append(self)

    def master_for(self, service_name: str, **kwargs: Any) -> FakeRedisClient:
        self.service_name = service_name
        self.master_kwargs = kwargs
        return self.master_client


def test_parse_sentinel_hosts_defaults_port() -> None:
    assert parse_sentinel_hosts("sentinel-a,sentinel-b:26380") == [
        ("sentinel-a", 26379),
        ("sentinel-b", 26380),
    ]


def test_parse_sentinel_url() -> None:
    hosts, master, db = _parse_sentinel_url("redis+sentinel://127.0.0.1:26379,127.0.0.2/mymaster/3")
    assert hosts == [("127.0.0.1", 26379), ("127.0.0.2", 26379)]
    assert master == "mymaster"
    assert db == 3


def test_from_sentinel_uses_master_client(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("redis")
    import redis.sentinel

    FakeSentinel.instances.clear()
    monkeypatch.setattr(redis.sentinel, "Sentinel", FakeSentinel)

    store = RedisStateStore.from_sentinel(
        "127.0.0.1:26379,127.0.0.1:26380",
        "as-master",
        "as",
        time.time,
        db=2,
    )
    key = store.build_key("translation", "call", "sentinel-1")
    store.set(key, b"ok", ttl_seconds=30.0)

    sentinel = FakeSentinel.instances[-1]
    assert sentinel.endpoints == [("127.0.0.1", 26379), ("127.0.0.1", 26380)]
    assert sentinel.service_name == "as-master"
    assert sentinel.master_kwargs == {"db": 2}
    assert sentinel.master_client.values[key] == b"ok"


def test_from_url_sentinel_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("redis")
    import redis.sentinel

    FakeSentinel.instances.clear()
    monkeypatch.setattr(redis.sentinel, "Sentinel", FakeSentinel)

    store = RedisStateStore.from_url(
        "redis+sentinel://127.0.0.1:26379/as-master/0",
        "as",
        time.time,
    )
    key = store.build_key("translation", "rate", "x")
    store.set(key, b"v", ttl_seconds=1.0)
    assert FakeSentinel.instances[-1].master_client.values[key] == b"v"


def test_load_redis_store_from_env_url(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("redis")
    captured: dict[str, str] = {}

    class RecordingRedis:
        @classmethod
        def from_url(cls, url: str) -> FakeRedisClient:
            captured["url"] = url
            return FakeRedisClient()

    redis_module = type("redis", (), {"Redis": RecordingRedis})
    monkeypatch.setitem(__import__("sys").modules, "redis", redis_module)
    monkeypatch.setenv("AS_REDIS_URL", "redis://127.0.0.1:6379/4")
    monkeypatch.delenv("AS_REDIS_SENTINEL_HOSTS", raising=False)
    monkeypatch.delenv("AS_REDIS_SENTINEL_MASTER", raising=False)

    store = load_redis_store_from_env(time.time)
    assert store is not None
    assert captured["url"] == "redis://127.0.0.1:6379/4"


def test_load_redis_store_from_env_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("redis")
    import redis.sentinel

    FakeSentinel.instances.clear()
    monkeypatch.setattr(redis.sentinel, "Sentinel", FakeSentinel)
    monkeypatch.delenv("AS_REDIS_URL", raising=False)
    monkeypatch.setenv("AS_REDIS_SENTINEL_HOSTS", "127.0.0.1:26379")
    monkeypatch.setenv("AS_REDIS_SENTINEL_MASTER", "as-master")

    store = load_redis_store_from_env(time.time)
    assert store is not None
    assert FakeSentinel.instances[-1].service_name == "as-master"


def test_load_redis_store_from_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AS_REDIS_URL", raising=False)
    monkeypatch.delenv("AS_REDIS_SENTINEL_HOSTS", raising=False)
    monkeypatch.delenv("AS_REDIS_SENTINEL_MASTER", raising=False)
    assert load_redis_store_from_env(time.time) is None
