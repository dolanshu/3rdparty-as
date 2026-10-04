"""Unit tests for the executable process-shell entry point."""

from __future__ import annotations

import signal
import socket
import time
from collections.abc import Callable

import pytest

from as_platform import __main__ as entrypoint
from as_platform.shell import ProcessShell, ShellConfig

pytestmark = pytest.mark.unit


class FakeClock:
    """A monotonic clock advanced by the injected sleep function."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _deliver_sigterm(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    handlers: dict[int, object] = {}
    installed_signals: list[int] = []

    def install_handler(signum: int, handler: object) -> object:
        handlers[signum] = handler
        if callable(handler):
            installed_signals.append(signum)
        return signal.SIG_DFL

    def pause() -> None:
        handler = handlers[signal.SIGTERM]
        assert callable(handler)
        handler(signal.SIGTERM, None)

    monkeypatch.setattr(entrypoint.signal, "getsignal", lambda _signum: signal.SIG_DFL)
    monkeypatch.setattr(entrypoint.signal, "signal", install_handler)
    monkeypatch.setattr(entrypoint.signal, "pause", pause)
    return installed_signals


def _capture_shell(
    monkeypatch: pytest.MonkeyPatch,
    active_calls_override: Callable[[], int] | None = None,
) -> list[ProcessShell]:
    shells: list[ProcessShell] = []
    real_build_shell = entrypoint.build_shell

    def capture(
        config: ShellConfig,
        active_calls: Callable[[], int],
        sleep: Callable[[float], None],
        now: Callable[[], float],
    ) -> ProcessShell:
        shell = real_build_shell(config, active_calls_override or active_calls, sleep, now)
        shells.append(shell)
        return shell

    monkeypatch.setattr(entrypoint, "build_shell", capture)
    return shells


def test_build_shell_accepts_new_requests() -> None:
    shell = entrypoint.build_shell(
        ShellConfig(drain_timeout_seconds=1.0),
        active_calls=lambda: 0,
        sleep=lambda _seconds: None,
        now=lambda: 0.0,
    )

    assert shell.accepts_new_requests() is True


def test_main_returns_zero_after_idle_process_receives_sigterm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    sleeps: list[float] = []
    installed_signals = _deliver_sigterm(monkeypatch)

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    monkeypatch.setattr(entrypoint.time, "sleep", sleep)
    monkeypatch.setattr(entrypoint.time, "monotonic", clock)

    exit_code = entrypoint.main(
        [
            "--drain-timeout-seconds",
            "1.0",
            "--poll-interval-seconds",
            "0.1",
            "--no-health-server",
        ]
    )

    assert exit_code == 0
    assert sleeps == []
    assert installed_signals == [signal.SIGTERM, signal.SIGINT]


def test_main_returns_nonzero_when_active_calls_do_not_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    sleeps: list[float] = []
    _deliver_sigterm(monkeypatch)
    _capture_shell(monkeypatch, active_calls_override=lambda: 1)

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)

    monkeypatch.setattr(entrypoint.time, "sleep", sleep)
    monkeypatch.setattr(entrypoint.time, "monotonic", clock)

    exit_code = entrypoint.main(
        [
            "--drain-timeout-seconds",
            "0.3",
            "--poll-interval-seconds",
            "0.1",
            "--no-health-server",
        ]
    )

    assert exit_code != 0
    assert clock.value >= 0.3
    assert sleeps


def test_termination_signal_stops_accepting_new_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shells = _capture_shell(monkeypatch)
    _deliver_sigterm(monkeypatch)
    monkeypatch.setattr(entrypoint.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(entrypoint.time, "monotonic", lambda: 0.0)

    assert entrypoint.main(["--no-health-server"]) == 0

    assert len(shells) == 1
    assert shells[0].accepts_new_requests() is False


def test_build_shell_reads_no_clock_and_opens_no_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def record(name: str) -> Callable[..., float]:
        def invoke(*_args: object, **_kwargs: object) -> float:
            calls.append(name)
            return 0.0

        return invoke

    monkeypatch.setattr(socket, "socket", record("socket.socket"))
    monkeypatch.setattr(time, "time", record("time.time"))
    monkeypatch.setattr(time, "monotonic", record("time.monotonic"))

    entrypoint.build_shell(
        ShellConfig(drain_timeout_seconds=1.0),
        active_calls=lambda: 0,
        sleep=lambda _seconds: None,
        now=time.monotonic,
    )

    assert calls == []
