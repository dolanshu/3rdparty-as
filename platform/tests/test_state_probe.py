"""Unit tests for Redis availability probe."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from as_platform.runtime.state_probe import probe_redis_available

pytestmark = pytest.mark.unit


def test_empty_url_is_unavailable() -> None:
    assert probe_redis_available("") is False
    assert probe_redis_available("   ") is False


def test_ping_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRedis:
        @classmethod
        def from_url(cls, _url: str, *, socket_connect_timeout: float) -> FakeRedis:
            assert socket_connect_timeout == 1.0
            return cls()

        def ping(self) -> bool:
            return True

    fake = ModuleType("redis")
    fake.Redis = FakeRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake)
    assert probe_redis_available("redis://127.0.0.1:6379/0") is True


def test_ping_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_url: str, *, socket_connect_timeout: float) -> Any:
        raise OSError("down")

    class FakeRedis:
        from_url = staticmethod(boom)

    fake = ModuleType("redis")
    fake.Redis = FakeRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake)
    assert probe_redis_available("redis://127.0.0.1:6379/0") is False
