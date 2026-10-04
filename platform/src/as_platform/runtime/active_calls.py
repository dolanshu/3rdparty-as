"""In-process active-call counting for draining and metrics (M5)."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable


def resolve_instance_id() -> str:
    """Return the pod/instance id used on metric labels.

    Prefers ``AS_INSTANCE_ID``, then Kubernetes ``POD_NAME`` / ``HOSTNAME``.
    """
    for key in ("AS_INSTANCE_ID", "POD_NAME", "HOSTNAME"):
        value = os.environ.get(key)
        if value:
            return value
    return "local"


def _simulated_hold_count() -> int:
    raw = os.environ.get("AS_M5_SIMULATED_ACTIVE_CALLS", "").strip()
    if not raw:
        return 0
    count = int(raw)
    if count < 0:
        raise ValueError("AS_M5_SIMULATED_ACTIVE_CALLS must be non-negative")
    return count


class ActiveCallSource:
    """Thread-safe active-call counter with optional M5 simulation hook.

    When ``AS_M5_SIMULATED_ACTIVE_CALLS`` is set, the count stays at that value
    until termination is requested, then linearly drains at one call per second
    so cluster draining/scale-down tests can observe non-zero ``active_calls``.
    """

    def __init__(
        self,
        *,
        is_terminating: Callable[[], bool],
        now: Callable[[], float],
    ) -> None:
        """Wire termination state and a monotonic clock for simulated drain."""
        self._lock = threading.Lock()
        self._manual = 0
        self._simulated_peak = _simulated_hold_count()
        self._terminate_started_at: float | None = None
        self._is_terminating = is_terminating
        self._now = now

    def increment(self, delta: int = 1) -> None:
        """Increase the manual in-flight call counter."""
        with self._lock:
            self._manual += delta

    def decrement(self, delta: int = 1) -> None:
        """Decrease the manual in-flight call counter."""
        with self._lock:
            self._manual = max(0, self._manual - delta)

    def count(self) -> int:
        """Return total in-flight calls (manual plus optional simulation)."""
        with self._lock:
            manual = self._manual
            if self._simulated_peak == 0:
                return manual
            if not self._is_terminating():
                return manual + self._simulated_peak
            if self._terminate_started_at is None:
                self._terminate_started_at = self._now()
            elapsed = max(0.0, self._now() - self._terminate_started_at)
            simulated = max(0, self._simulated_peak - int(elapsed))
            return manual + simulated
