"""Unit tests for process shell draining, with an injected clock and sleep.

Acceptance: docs/acceptance/test-plan.md §5.5. See ADR-0009 (skeleton) and
ADR-0002 (the process holds no state, so draining needs no migration).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from as_platform.shell import ProcessShell, ShellConfig

pytestmark = pytest.mark.unit


class FakeClock:
    """A clock the test advances through the injected sleep."""

    def __init__(self) -> None:
        self.now_value = 0.0

    def __call__(self) -> float:
        return self.now_value

    def advance(self, seconds: float) -> None:
        self.now_value += seconds


def _build(
    active_calls: Callable[[], int],
    clock: FakeClock,
    drain_timeout_seconds: float = 1.0,
) -> tuple[ProcessShell, list[float]]:
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    shell = ProcessShell(
        config=ShellConfig(drain_timeout_seconds=drain_timeout_seconds, poll_interval_seconds=0.1),
        active_calls=active_calls,
        sleep=sleep,
        now=clock,
    )
    return shell, sleeps


def test_new_requests_are_accepted_until_termination() -> None:
    """Draining starts by refusing new requests."""
    shell, _ = _build(lambda: 0, FakeClock())

    assert shell.accepts_new_requests() is True

    shell.request_terminate()

    assert shell.accepts_new_requests() is False


def test_terminate_with_no_active_calls_returns_immediately() -> None:
    """An idle process exits at once and never sleeps. Case 1."""
    clock = FakeClock()
    shell, sleeps = _build(lambda: 0, clock)

    shell.request_terminate()

    assert shell.run_until_drained() is True
    assert sleeps == []
    assert clock.now_value == 0.0


def test_terminate_waits_until_active_calls_reach_zero() -> None:
    """In-flight calls are drained before the process exits. Case 2."""
    clock = FakeClock()
    remaining = iter([3, 2, 1, 0])
    shell, sleeps = _build(lambda: next(remaining), clock)

    shell.request_terminate()

    assert shell.run_until_drained() is True
    assert len(sleeps) == 3


def test_drain_timeout_forces_an_exit() -> None:
    """A process that never drains exits anyway; the wait is bounded. Case 3."""
    clock = FakeClock()
    shell, sleeps = _build(lambda: 2, clock, drain_timeout_seconds=1.0)

    shell.request_terminate()

    assert shell.run_until_drained() is False
    assert clock.now_value >= 1.0
    assert len(sleeps) <= 20
