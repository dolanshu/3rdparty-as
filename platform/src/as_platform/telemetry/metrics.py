"""In-process metrics: names and semantics only, no thresholds.

This module is the seam between the call path and whatever exports metrics
(OTel today, anything else later). It deliberately defines **only** the metric
names of the alert contract in ``deploy/alerts/README.md`` and their meaning:

* :data:`ACTIVE_CALLS` — calls in flight, per instance. The scale-down guard
  needs the per-instance number, because an aggregate average can be low while
  one instance still carries calls (ADR-0010).
* :data:`SIP_RESPONSES_TOTAL` — SIP responses by class and code.
* :data:`RULE_HITS_TOTAL` — decisions taken by rule.
* :data:`TELEMETRY_DROPPED_TOTAL` — events the bounded queue discarded.

**There is no capacity number here.** No threshold, no target, no default: O1
(the capacity target) is measured in M6, and publishing a figure before that
measurement exists is forbidden (AGENT.md §2, plan.md §6). A metric definition
is not a capacity conclusion.

The registry is pure: it reads no clock and performs no IO, so a test can prove
that with a monkeypatch and production can call it from a SIP callback. Export
goes through :func:`emit_snapshot`, which hands events to the ADR-0005 sink —
enqueue and return, never block, never raise.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from as_platform.telemetry import TelemetryEvent, TelemetrySink

ACTIVE_CALLS = "as_active_calls"
SIP_RESPONSES_TOTAL = "as_sip_responses_total"
RULE_HITS_TOTAL = "as_rule_hits_total"
TELEMETRY_DROPPED_TOTAL = "as_telemetry_dropped_total"

_METRIC_EVENT_PREFIX = "metric."
_LABEL_POD = "pod"
_LABEL_USE_CASE = "use_case"
_LABEL_STATUS_CODE = "status_code"
_LABEL_STATUS_CLASS = "status_class"
_LABEL_RULE = "rule"


class MetricKind(Enum):
    """How a metric is written: counters add up, gauges are overwritten."""

    COUNTER = "counter"
    GAUGE = "gauge"


@dataclass(frozen=True)
class MetricPoint:
    """One metric series at one instant.

    Attributes:
        name: The metric name, as spelled in the alert contract.
        kind: Whether the series accumulates or is overwritten.
        value: The current value.
        labels: The dimension set that identifies this series.
    """

    name: str
    kind: MetricKind
    value: float
    labels: Mapping[str, str]


def _series_key(
    name: str,
    labels: Mapping[str, str] | None,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Build the identity of one series.

    Args:
        name: The metric name.
        labels: The dimensions, or ``None`` for an unlabelled series.

    Returns:
        The name plus the label pairs sorted by key, so two label sets written
        in a different order name the same series.
    """
    items = tuple(sorted((labels or {}).items()))
    return (name, items)


class MetricsRegistry:
    """The in-process metric store: thread-safe, clock-free, IO-free.

    Every update takes a lock, so concurrent writers — one per SIP worker
    thread in practice — cannot lose an increment. Reading a snapshot also
    takes the lock, so a reader never sees a half-applied update.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._values: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._kinds: dict[tuple[str, tuple[tuple[str, str], ...]], MetricKind] = {}
        self._lock = threading.Lock()

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Overwrite one gauge series.

        Args:
            name: The metric name.
            value: The current value; a later call replaces it.
            labels: The dimensions identifying the series.
        """
        key = _series_key(name, labels)
        with self._lock:
            self._kinds[key] = MetricKind.GAUGE
            self._values[key] = float(value)

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        """Add to one counter series.

        Args:
            name: The metric name.
            value: How much to add; defaults to one event.
            labels: The dimensions identifying the series.
        """
        key = _series_key(name, labels)
        with self._lock:
            self._kinds[key] = MetricKind.COUNTER
            self._values[key] = self._values.get(key, 0.0) + float(value)

    def snapshot(self) -> tuple[MetricPoint, ...]:
        """Read every series, in a deterministic order.

        The order is by metric name and then by the sorted label pairs, so the
        same registry always yields the same tuple: snapshots can be compared,
        diffed and asserted on.

        Returns:
            One :class:`MetricPoint` per series, deterministically ordered.
        """
        with self._lock:
            return tuple(
                MetricPoint(
                    name=name,
                    kind=self._kinds[(name, label_items)],
                    value=self._values[(name, label_items)],
                    labels=dict(label_items),
                )
                for name, label_items in sorted(self._values)
            )


class CallMetrics:
    """The domain facade: what the call path and the ops layer actually call.

    It writes the metric names of the alert contract so that a rule and the
    code that feeds it cannot drift apart silently.
    """

    def __init__(self, registry: MetricsRegistry) -> None:
        """Create a facade over one registry.

        Args:
            registry: Where the series are stored.
        """
        self._registry = registry

    def set_active_calls(self, instance_id: str, use_case: str, count: int) -> None:
        """Report how many calls this instance is carrying right now.

        Args:
            instance_id: The identity of the instance, a pod name in practice.
            use_case: The use case the instance serves.
            count: Calls currently in flight on it.
        """
        self._registry.set_gauge(
            ACTIVE_CALLS,
            float(count),
            {_LABEL_POD: instance_id, _LABEL_USE_CASE: use_case},
        )

    def active_calls_for(self, instance_id: str) -> int:
        """Read the calls in flight on one instance, as the guard needs it.

        An aggregate average is what makes scale-down unsafe, so this is the
        per-instance number: the scale-down guard refuses to remove an instance
        that is still carrying calls. See ADR-0010.

        Args:
            instance_id: The identity of the instance.

        Returns:
            Calls in flight on that instance; ``0`` when it never reported,
            which is also the answer that lets the guard proceed.
        """
        total = 0.0
        for point in self._registry.snapshot():
            if point.name == ACTIVE_CALLS and point.labels.get(_LABEL_POD) == instance_id:
                total += point.value
        return int(total)

    def record_response(self, use_case: str, status_code: int) -> None:
        """Count one SIP response by use case, class, and exact code.

        Args:
            use_case: The use case that produced the response.
            status_code: The SIP status code sent, for example ``603``.

        Raises:
            ValueError: If the code is outside 100..699, so a typo cannot
                create a nonsense class instead of being noticed.
        """
        if not 100 <= status_code <= 699:
            raise ValueError(f"not a SIP status code: {status_code}")

        self._registry.increment(
            SIP_RESPONSES_TOTAL,
            labels={
                _LABEL_USE_CASE: use_case,
                _LABEL_STATUS_CLASS: f"{status_code // 100}xx",
                _LABEL_STATUS_CODE: str(status_code),
            },
        )

    def record_rule_hit(self, rule_id: str) -> None:
        """Count one decision taken by a rule.

        Args:
            rule_id: The rule that decided the call.
        """
        self._registry.increment(RULE_HITS_TOTAL, labels={_LABEL_RULE: rule_id})

    def record_telemetry_dropped(self, use_case: str, count: int = 1) -> None:
        """Count telemetry events the bounded queue discarded.

        Args:
            use_case: The use case whose telemetry was dropped.
            count: How many events were dropped; defaults to one.
        """
        self._registry.increment(
            TELEMETRY_DROPPED_TOTAL,
            float(count),
            labels={_LABEL_USE_CASE: use_case},
        )


def emit_snapshot(sink: TelemetrySink, registry: MetricsRegistry) -> None:
    """Hand the current snapshot to the sink, without ever blocking the caller.

    One event per series, carrying the value and the labels as attributes. The
    timestamp stays at zero: this module reads no clock, and filling it in is
    the exporter's job. A sink that is full drops the event, and a sink that
    raises is swallowed — losing telemetry is acceptable, applying back
    pressure to call setup is not. See ADR-0005.

    Args:
        sink: Where the events go.
        registry: The registry to read.
    """
    for point in registry.snapshot():
        attributes = dict(point.labels)
        attributes["value"] = str(point.value)
        attributes["metric_kind"] = point.kind.value
        try:
            sink.emit(
                TelemetryEvent(
                    name=f"{_METRIC_EVENT_PREFIX}{point.name}",
                    attributes=attributes,
                )
            )
        except Exception:  # a broken backend must not slow the call path. See ADR-0005
            continue
