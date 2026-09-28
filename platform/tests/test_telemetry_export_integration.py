"""Integration tests for telemetry export over a real UDP socket.

The promise under test is ADR-0005: the call path only ever calls ``emit()``,
which enqueues and returns. The socket write happens on the export thread, never
inside a SIP callback; when the queue is full the event is **dropped** instead of
applying back pressure to call setup.

These are the repository's first ``integration`` cases, so they speak to a real
socket on loopback. The port is whatever the OS hands out -- bound to port 0 and
read back -- so parallel runs cannot collide (AGENT.md §6).

Acceptance: docs/acceptance/test-plan.md §5.4.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

from as_platform.telemetry import BoundedQueueSink, TelemetryEvent

pytestmark = pytest.mark.integration

_HOST = "127.0.0.1"
_MAX_DATAGRAM_BYTES = 65535
_RECEIVE_TIMEOUT_SECONDS = 0.05
_DELIVERY_TIMEOUT_SECONDS = 5.0
_JOIN_TIMEOUT_SECONDS = 2.0
_EMIT_BUDGET_SECONDS = 1.0
_OVERFLOW_EVENT_COUNT = 2000
_OVERFLOW_QUEUE_CAPACITY = 1


class UdpExporter:
    """The backend-facing half: one JSON line per event, sent as a UDP datagram.

    It lives in the test rather than in ``src/``: the kernel API stays clean
    while the integration test still writes to a real socket. See ADR-0005.

    Attributes:
        threads: Every thread ``export`` was called on, so the test can prove the
            write never happened on the caller's thread.
    """

    def __init__(self, host: str, port: int) -> None:
        """Create an exporter writing to ``(host, port)``.

        Args:
            host: The loopback address the collector is bound to.
            port: The OS-assigned port the collector listens on.
        """
        self._address = (host, port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.threads: list[threading.Thread] = []

    def export(self, events: Sequence[TelemetryEvent]) -> None:
        """Send one datagram per event.

        Args:
            events: The batch drained from the queue.
        """
        self.threads.append(threading.current_thread())
        for event in events:
            payload = json.dumps(
                {
                    "name": event.name,
                    "attributes": dict(event.attributes),
                    "timestamp": event.timestamp,
                },
                sort_keys=True,
            )
            self._socket.sendto(payload.encode("utf-8"), self._address)

    def close(self) -> None:
        """Release the socket when the sink no longer needs it."""
        self._socket.close()


class UdpCollector:
    """A loopback UDP receiver that keeps every datagram it is sent.

    The port comes from the OS: the socket binds to port 0 and the real port is
    read back, so no test owns a fixed port (AGENT.md §6).

    Attributes:
        host: The address the socket is bound to.
        port: The port the OS assigned.
    """

    def __init__(self) -> None:
        """Bind a socket to an OS-assigned loopback port; start no thread yet."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.settimeout(_RECEIVE_TIMEOUT_SECONDS)
        self._socket.bind((_HOST, 0))
        address = self._socket.getsockname()
        self.host = str(address[0])
        self.port = int(address[1])
        self._condition = threading.Condition()
        self._payloads: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the receive thread; without it nothing reads the socket."""
        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._receive, name="test-udp-collector", daemon=True
        )
        self._thread.start()

    def wait_for_events(self, count: int, timeout: float) -> list[dict[str, Any]]:
        """Wait until at least ``count`` datagrams have arrived.

        The wait is bounded: it ends on the condition or on the timeout, never on
        a fixed sleep, and a timeout is a failure rather than an empty result.

        Args:
            count: How many datagrams to wait for.
            timeout: How long to wait, in seconds.

        Returns:
            The decoded payloads, oldest first; at least ``count`` of them.
        """
        with self._condition:
            arrived = self._condition.wait_for(lambda: len(self._payloads) >= count, timeout)
            if not arrived:
                raise AssertionError(
                    f"only {len(self._payloads)} of {count} datagrams arrived in {timeout} seconds"
                )
            return [json.loads(payload) for payload in self._payloads[:count]]

    def _receive(self) -> None:
        """Read datagrams until the socket is closed."""
        while not self._stop.is_set():
            try:
                payload, _ = self._socket.recvfrom(_MAX_DATAGRAM_BYTES)
            except TimeoutError:
                continue
            except OSError:
                # The socket was closed by `close()`; nothing more will arrive.
                return

            with self._condition:
                self._payloads.append(payload.decode("utf-8"))
                self._condition.notify_all()

    def close(self) -> None:
        """Stop receiving and release the socket."""
        self._stop.set()
        self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=_JOIN_TIMEOUT_SECONDS)


@pytest.fixture
def collector() -> Iterator[UdpCollector]:
    """A bound collector whose receive thread is running."""
    receiver = UdpCollector()
    receiver.start()
    try:
        yield receiver
    finally:
        receiver.close()


@pytest.fixture
def unread_collector() -> Iterator[UdpCollector]:
    """A bound collector nobody reads: the backend exists but never consumes."""
    receiver = UdpCollector()
    try:
        yield receiver
    finally:
        receiver.close()


def _event(index: int) -> TelemetryEvent:
    """Build one event whose payload identifies it on the wire.

    Args:
        index: The position of the event in the burst that is emitted.

    Returns:
        A telemetry event carrying that index in its name and attributes.
    """
    return TelemetryEvent(
        name=f"call.decided.{index}",
        attributes={"call_id": f"call-{index}"},
        timestamp=float(index),
    )


def test_emitted_events_reach_the_udp_collector(collector: UdpCollector) -> None:
    """A real socket carries the events out, on a thread that is not the caller. Case 1."""
    exporter = UdpExporter(collector.host, collector.port)
    sink = BoundedQueueSink(capacity=8, exporter=exporter, poll_interval_seconds=0.01)

    sink.start()
    try:
        for index in range(3):
            sink.emit(_event(index))
        received = collector.wait_for_events(3, timeout=_DELIVERY_TIMEOUT_SECONDS)
    finally:
        sink.stop(timeout=_JOIN_TIMEOUT_SECONDS)
        exporter.close()

    assert sorted(payload["name"] for payload in received) == [
        "call.decided.0",
        "call.decided.1",
        "call.decided.2",
    ]
    delivered = {payload["name"]: payload for payload in received}
    assert delivered["call.decided.1"]["attributes"] == {"call_id": "call-1"}
    assert delivered["call.decided.1"]["timestamp"] == 1.0
    assert sink.dropped_count == 0
    assert sink.export_failure_count == 0
    assert exporter.threads[0].ident != threading.current_thread().ident


def test_emit_never_blocks_and_drops_when_the_queue_is_full(
    unread_collector: UdpCollector,
) -> None:
    """Overflow costs telemetry, never call-setup latency. Case 2, ADR-0005."""
    exporter = UdpExporter(unread_collector.host, unread_collector.port)
    sink = BoundedQueueSink(
        capacity=_OVERFLOW_QUEUE_CAPACITY,
        exporter=exporter,
        batch_size=1,
        poll_interval_seconds=0.01,
    )

    sink.start()
    try:
        started = time.monotonic()
        for index in range(_OVERFLOW_EVENT_COUNT):
            sink.emit(_event(index))
        elapsed = time.monotonic() - started
    finally:
        sink.stop(timeout=_JOIN_TIMEOUT_SECONDS)
        exporter.close()

    assert elapsed < _EMIT_BUDGET_SECONDS, (
        f"{_OVERFLOW_EVENT_COUNT} emits took {elapsed:.3f}s, the budget is {_EMIT_BUDGET_SECONDS}s"
    )
    assert sink.dropped_count > 0, "a full queue must drop, never apply back pressure"


def test_stop_leaves_no_export_thread_behind(collector: UdpCollector) -> None:
    """`stop(timeout)` joins the export thread: nothing writes after it returns. Case 3."""
    exporter = UdpExporter(collector.host, collector.port)
    sink = BoundedQueueSink(capacity=8, exporter=exporter, poll_interval_seconds=0.01)

    sink.start()
    try:
        sink.emit(_event(0))
        received = collector.wait_for_events(1, timeout=_DELIVERY_TIMEOUT_SECONDS)
    finally:
        sink.stop(timeout=_JOIN_TIMEOUT_SECONDS)
        exporter.close()

    assert received[0]["name"] == "call.decided.0"
    export_thread = exporter.threads[0]
    assert export_thread.ident != threading.current_thread().ident
    assert not export_thread.is_alive(), "the export thread outlived stop()"
