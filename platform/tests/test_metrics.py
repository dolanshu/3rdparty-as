"""Unit tests for the metrics seam: names and semantics, no thresholds.

The registry holds the metric names of the alert contract
(``deploy/alerts/README.md``), ``CallMetrics`` is the per-instance view the
scale-down guard consumes (ADR-0010), and export must never block the call
path (ADR-0005).

There is deliberately no capacity number anywhere in these tests: O1 is
measured in M6.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from as_platform.telemetry import BoundedQueueSink, TelemetryEvent
from as_platform.telemetry.metrics import (
    CallMetrics,
    MetricKind,
    MetricPoint,
    MetricsRegistry,
    emit_snapshot,
)

pytestmark = pytest.mark.unit

_THREAD_COUNT = 8
_INCREMENTS_PER_THREAD = 500
_JOIN_TIMEOUT_SECONDS = 10.0
_BARRIER_TIMEOUT_SECONDS = 10.0
_NON_BLOCKING_BUDGET_SECONDS = 1.0

# Source: deploy/alerts/README.md, "Metric contract".
_ACTIVE_CALLS_LABELS = ("pod", "use_case")
_SIP_RESPONSES_LABELS = ("status_class", "status_code", "use_case")


class RecordingSink:
    """Collects the events it is handed; performs no IO of its own."""

    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def emit(self, event: TelemetryEvent) -> None:
        self.events.append(event)


class ExplodingSink:
    """A broken backend: every emit raises. Losing telemetry stays silent."""

    def emit(self, event: TelemetryEvent) -> None:
        raise RuntimeError("backend unreachable")


def _points(registry: MetricsRegistry, name: str) -> tuple[MetricPoint, ...]:
    """Return the series recorded under ``name``, in snapshot order.

    Args:
        registry: The registry to read.
        name: The metric name to filter on.

    Returns:
        Every point with that name, ordered as :meth:`MetricsRegistry.snapshot`
        returns them.
    """
    return tuple(point for point in registry.snapshot() if point.name == name)


def _point(registry: MetricsRegistry, name: str) -> MetricPoint:
    """Return the only series recorded under ``name``.

    Args:
        registry: The registry to read.
        name: The metric name to filter on.

    Returns:
        The single point with that name; fails loudly if there are none or many.
    """
    points = _points(registry, name)
    assert len(points) == 1, f"expected exactly one series for {name}, got {points}"
    return points[0]


def test_a_gauge_overwrites_and_a_counter_accumulates() -> None:
    """Writing a gauge replaces the previous value; incrementing adds to it. Case 1."""
    registry = MetricsRegistry()

    registry.set_gauge("as_active_calls", 3.0, {"pod": "pod-a"})
    registry.set_gauge("as_active_calls", 7.0, {"pod": "pod-a"})
    registry.increment("as_sip_responses_total")
    registry.increment("as_sip_responses_total", 2.5)

    gauge = _point(registry, "as_active_calls")
    counter = _point(registry, "as_sip_responses_total")

    assert gauge.value == 7.0, "a later gauge write must replace the earlier one"
    assert gauge.kind is MetricKind.GAUGE
    assert counter.value == 3.5, "a counter must accumulate, defaulting to +1"
    assert counter.kind is MetricKind.COUNTER


def test_series_with_different_labels_are_isolated() -> None:
    """The same metric name under different labels is two series, not one. Case 2."""
    registry = MetricsRegistry()

    registry.set_gauge("as_active_calls", 1.0, {"pod": "pod-a"})
    registry.set_gauge("as_active_calls", 2.0, {"pod": "pod-b"})

    points = _points(registry, "as_active_calls")
    assert len(points) == 2, "labels must not collapse into one series"
    assert [dict(point.labels) for point in points] == [
        {"pod": "pod-a"},
        {"pod": "pod-b"},
    ]
    assert [point.value for point in points] == [1.0, 2.0]


def test_snapshot_order_is_deterministic() -> None:
    """The same registry yields the same order every time, by name then labels. Case 3."""
    registry = MetricsRegistry()

    registry.increment("z_total", labels={"b": "2", "a": "1"})
    registry.set_gauge("a_gauge", 1.0, {"z": "1", "a": "2"})
    registry.increment("a_total", labels={"k": "v"})
    registry.set_gauge("m_gauge", 1.0, {"k": "b"})
    registry.set_gauge("m_gauge", 2.0, {"k": "a"})

    snapshots = [registry.snapshot() for _ in range(3)]

    assert snapshots[0] == snapshots[1] == snapshots[2], "snapshot order must be stable"
    names = [point.name for point in snapshots[0]]
    assert names == sorted(names), f"names are not sorted: {names}"
    assert [point.labels["k"] for point in _points(registry, "m_gauge")] == ["a", "b"]


def test_concurrent_increments_keep_every_update() -> None:
    """A counter updated from many threads loses nothing: threads x increments. Case 4."""
    registry = MetricsRegistry()
    barrier = threading.Barrier(_THREAD_COUNT)

    def worker() -> None:
        barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
        for _ in range(_INCREMENTS_PER_THREAD):
            registry.increment("as_sip_responses_total")

    threads = [threading.Thread(target=worker) for _ in range(_THREAD_COUNT)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_JOIN_TIMEOUT_SECONDS)

    expected = float(_THREAD_COUNT * _INCREMENTS_PER_THREAD)
    assert _point(registry, "as_sip_responses_total").value == expected


def test_active_calls_are_readable_per_instance() -> None:
    """The scale-down guard needs the count of one instance, not an average. Case 5, ADR-0010."""
    registry = MetricsRegistry()
    metrics = CallMetrics(registry)

    metrics.set_active_calls("pod-a", "use-case-1", 7)

    point = _point(registry, "as_active_calls")
    assert point.name == "as_active_calls"
    assert point.kind is MetricKind.GAUGE
    assert dict(point.labels) == {"pod": "pod-a", "use_case": "use-case-1"}
    assert metrics.active_calls_for("pod-a") == 7

    metrics.set_active_calls("pod-b", "use-case-1", 3)
    assert metrics.active_calls_for("pod-b") == 3
    assert metrics.active_calls_for("pod-a") == 7, "a second instance must not move the first"


def test_active_calls_for_an_unknown_instance_is_zero() -> None:
    """No data means no calls in flight, which is what the guard needs to know. Case 5."""
    metrics = CallMetrics(MetricsRegistry())

    assert metrics.active_calls_for("pod-never-reported") == 0


def test_record_response_classifies_by_status_code() -> None:
    """603 lands in class 6xx and 404 in 4xx; the exact code is kept. Case 6."""
    registry = MetricsRegistry()
    metrics = CallMetrics(registry)

    metrics.record_response("use-case-1", 603)
    metrics.record_response("use-case-1", 603)
    metrics.record_response("use-case-1", 404)
    metrics.record_response("use-case-1", 200)

    points = _points(registry, "as_sip_responses_total")
    by_status = {point.labels["status_code"]: point for point in points}

    assert sorted(by_status) == ["200", "404", "603"]
    assert by_status["603"].labels["status_class"] == "6xx"
    assert by_status["404"].labels["status_class"] == "4xx"
    assert by_status["200"].labels["status_class"] == "2xx"
    assert all(point.labels["use_case"] == "use-case-1" for point in points)
    assert by_status["603"].value == 2.0, "two declines must accumulate"
    assert by_status["404"].value == 1.0


def test_alert_metric_label_sets_match_the_contract() -> None:
    """Alert-facing metric labels exactly match the source contract."""
    registry = MetricsRegistry()
    metrics = CallMetrics(registry)

    metrics.set_active_calls("pod-a", "use-case-1", 1)
    metrics.record_response("use-case-1", 503)

    assert tuple(_point(registry, "as_active_calls").labels) == _ACTIVE_CALLS_LABELS
    assert tuple(_point(registry, "as_sip_responses_total").labels) == _SIP_RESPONSES_LABELS


def test_emit_snapshot_drops_instead_of_blocking() -> None:
    """A full sink costs telemetry, never call-setup latency. Case 7, ADR-0005."""
    registry = MetricsRegistry()
    metrics = CallMetrics(registry)
    metrics.set_active_calls("pod-a", "use-case-1", 1)
    metrics.record_response("use-case-1", 200)
    metrics.record_telemetry_dropped("use-case-1", 3)
    sink = BoundedQueueSink(capacity=1)

    started = time.monotonic()
    emit_snapshot(sink, registry)  # must not raise and must not wait
    elapsed = time.monotonic() - started

    assert elapsed < _NON_BLOCKING_BUDGET_SECONDS, (
        f"emit_snapshot took {elapsed:.3f}s, budget is {_NON_BLOCKING_BUDGET_SECONDS}s"
    )
    assert sink.dropped_count > 0, "events beyond the sink capacity must be dropped"
    emit_snapshot(ExplodingSink(), registry)  # a broken backend must stay silent


def test_metrics_read_no_clock_and_open_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module is pure: no clock, no socket, timestamps left at zero. Case 8."""
    calls: list[str] = []

    def fake_socket(*args: object, **kwargs: object) -> None:
        calls.append("socket")

    def fake_clock() -> float:
        calls.append("clock")
        return 0.0

    monkeypatch.setattr(socket, "socket", fake_socket)
    monkeypatch.setattr(time, "time", fake_clock)
    monkeypatch.setattr(time, "monotonic", fake_clock)

    registry = MetricsRegistry()
    metrics = CallMetrics(registry)
    metrics.set_active_calls("pod-a", "use-case-1", 2)
    metrics.record_response("use-case-1", 487)
    metrics.record_rule_hit("rule-1")
    metrics.record_telemetry_dropped("use-case-1")
    recording = RecordingSink()

    emit_snapshot(recording, registry)
    _ = metrics.active_calls_for("pod-a")

    assert calls == [], f"the metrics seam touched the outside world: {calls}"
    assert len(recording.events) == 4
    assert all(event.timestamp == 0.0 for event in recording.events)
