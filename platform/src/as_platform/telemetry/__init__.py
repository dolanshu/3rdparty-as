"""Telemetry: a bounded queue with a background exporter and a no-op default.

The call path only ever calls ``emit()``, which enqueues and returns. When the
queue is full the event is **dropped** and ``dropped_count`` is incremented:
losing telemetry is acceptable, applying back pressure to call setup is not
(ADR-0005). Export runs on its own thread, never inside a SIP callback.

The default sink is :class:`NoOpSink`, so an unconfigured deployment pays
nothing and tests need no backend.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class TelemetryEvent:
    """One telemetry record.

    Attributes:
        name: The event name, for example ``call.decided``.
        attributes: String-valued attributes attached to the event.
        timestamp: When the event happened, injected by the caller.
    """

    name: str
    attributes: Mapping[str, str] = field(default_factory=dict)
    timestamp: float = 0.0


class Exporter(Protocol):
    """The backend-facing half: it receives batches off the call path."""

    def export(self, events: Sequence[TelemetryEvent]) -> None:
        """Hand one batch to the backend.

        Args:
            events: The events drained from the queue.
        """
        ...


class NoOpSink:
    """The default sink: ``emit()`` does nothing and cannot fail."""

    def emit(self, event: TelemetryEvent) -> None:
        """Discard an event.

        Args:
            event: The event to discard.
        """
        del event  # intentionally unused


class NoOpExporter:
    """The default exporter: batches are discarded."""

    def export(self, events: Sequence[TelemetryEvent]) -> None:
        """Discard a batch.

        Args:
            events: The events drained from the queue.
        """
        del events  # intentionally unused


def default_sink() -> NoOpSink:
    """Return the sink used when telemetry is not configured.

    Returns:
        A :class:`NoOpSink`.
    """
    return NoOpSink()


class BoundedQueueSink:
    """The only sink the call path may touch: enqueue, then return.

    Attributes:
        capacity: How many events the queue holds before dropping.
    """

    def __init__(
        self,
        capacity: int,
        exporter: Exporter | None = None,
        batch_size: int = 32,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        """Create a sink.

        Args:
            capacity: The maximum number of queued events; must be positive.
            exporter: Where batches go; defaults to :class:`NoOpExporter`.
            batch_size: How many events are handed to the exporter at once.
            poll_interval_seconds: How long the export thread waits on an empty
                queue before noticing a stop request.

        Raises:
            ValueError: If ``capacity`` is not positive.
        """
        if capacity < 1:
            raise ValueError(f"capacity must be positive, got {capacity}")

        self.capacity = capacity
        self._queue: queue.Queue[TelemetryEvent] = queue.Queue(maxsize=capacity)
        self._exporter = exporter if exporter is not None else NoOpExporter()
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds
        self._dropped = 0
        self._failures = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def dropped_count(self) -> int:
        """How many events were dropped because the queue was full.

        Returns:
            The number of dropped events.
        """
        with self._lock:
            return self._dropped

    @property
    def export_failure_count(self) -> int:
        """How many export attempts raised; a broken backend stops telemetry.

        Returns:
            The number of failed export attempts.
        """
        with self._lock:
            return self._failures

    def emit(self, event: TelemetryEvent) -> None:
        """Enqueue one event without ever blocking or raising.

        Args:
            event: The event to record.
        """
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            # Dropping is the designed behaviour: telemetry loss is acceptable,
            # back pressure on the call path is not. See ADR-0005.
            with self._lock:
                self._dropped += 1

    def start(self) -> None:
        """Start the background export thread; calling twice is a no-op."""
        if self._thread is not None:
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._drain, name="as-telemetry-export", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        """Ask the export thread to finish and wait for it.

        Args:
            timeout: How long to wait for the thread to join, in seconds.
        """
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            self._thread = None

    def _drain(self) -> None:
        """Consume the queue and hand batches to the exporter, forever."""
        while True:
            try:
                event = self._queue.get(timeout=self._poll_interval_seconds)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue

            batch = [event]
            while len(batch) < self._batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            try:
                self._exporter.export(batch)
            except Exception:  # noqa: BLE001 - a broken backend must not stop the loop
                with self._lock:
                    self._failures += 1
