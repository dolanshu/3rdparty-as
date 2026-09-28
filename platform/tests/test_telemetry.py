"""Unit tests for the telemetry queue: it must never block the call path.

Acceptance: docs/acceptance/test-plan.md §5.4. See ADR-0005.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Sequence

import pytest

from as_platform.telemetry import (
    BoundedQueueSink,
    NoOpSink,
    TelemetryEvent,
    default_sink,
)

pytestmark = pytest.mark.unit


def _event(name: str = "call.decided") -> TelemetryEvent:
    return TelemetryEvent(name=name, attributes={"call_id": "call-1"}, timestamp=0.0)


class RecordingExporter:
    """Collects the batches it is handed; performs no IO of its own."""

    def __init__(self) -> None:
        self.batches: list[Sequence[TelemetryEvent]] = []
        self.thread_idents: list[int | None] = []

    def export(self, events: Sequence[TelemetryEvent]) -> None:
        self.batches.append(tuple(events))
        self.thread_idents.append(threading.current_thread().ident)


class BlockingExporter:
    """Signals entry, then waits until the test releases it."""

    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self._entered = entered
        self._release = release
        self.completed = threading.Event()
        self.thread_idents: list[int | None] = []

    def export(self, events: Sequence[TelemetryEvent]) -> None:
        self.thread_idents.append(threading.current_thread().ident)
        self._entered.set()
        self._release.wait(timeout=5.0)
        self.completed.set()


def test_emit_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Export happens off the call path, and neither step touches the network. Case 1."""
    sockets: list[str] = []

    def fake_socket(*args: object, **kwargs: object) -> None:
        sockets.append("socket")

    monkeypatch.setattr(socket, "socket", fake_socket)
    exporter = RecordingExporter()
    sink = BoundedQueueSink(capacity=4, exporter=exporter, poll_interval_seconds=0.01)

    sink.start()
    sink.emit(_event())
    sink.stop(timeout=2.0)

    assert exporter.batches == [(_event(),)]
    assert sockets == []


def test_a_full_queue_drops_instead_of_raising() -> None:
    """Overflow is a design choice, not an error: dropped increments. Case 2, ADR-0005."""
    sink = BoundedQueueSink(capacity=1, exporter=RecordingExporter())

    for index in range(5):
        sink.emit(_event(f"call.decided.{index}"))

    assert sink.dropped_count == 4


def test_the_default_sink_is_the_no_op_sink() -> None:
    """Without configuration nothing is collected and nothing fails. Case 3."""
    sink = default_sink()

    assert isinstance(sink, NoOpSink)
    sink.emit(_event())


def test_a_sink_without_exporter_accepts_events() -> None:
    """The default exporter is the no-op one; start/emit/stop stay safe."""
    sink = BoundedQueueSink(capacity=2)

    sink.start()
    sink.emit(_event())
    sink.stop(timeout=2.0)

    assert sink.dropped_count == 0


def test_export_runs_on_another_thread_and_emit_does_not_wait() -> None:
    """The call path only enqueues; a slow exporter cannot delay it. Case 4."""
    entered = threading.Event()
    release = threading.Event()
    exporter = BlockingExporter(entered, release)
    sink = BoundedQueueSink(capacity=4, exporter=exporter, poll_interval_seconds=0.01)

    sink.start()
    try:
        sink.emit(_event())

        assert entered.wait(timeout=2.0), "the export thread never ran"
        assert exporter.thread_idents[0] != threading.current_thread().ident
        assert not exporter.completed.is_set(), "emit waited for the export to finish"
    finally:
        release.set()
        sink.stop(timeout=2.0)
