"""Unit tests for active-call counting and M5 simulation."""

from __future__ import annotations

import pytest

from as_platform.runtime.active_calls import ActiveCallSource

pytestmark = pytest.mark.unit


def test_manual_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AS_M5_SIMULATED_ACTIVE_CALLS", raising=False)
    terminating = False
    source = ActiveCallSource(is_terminating=lambda: terminating, now=lambda: 0.0)
    source.increment(2)
    assert source.count() == 2
    source.decrement(1)
    assert source.count() == 1


def test_simulated_calls_drain_after_terminate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AS_M5_SIMULATED_ACTIVE_CALLS", "3")
    terminating = False
    clock = 0.0

    def now() -> float:
        return clock

    source = ActiveCallSource(is_terminating=lambda: terminating, now=now)
    assert source.count() == 3
    terminating = True
    assert source.count() == 3
    clock = 1.5
    assert source.count() == 2
