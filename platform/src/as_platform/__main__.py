"""Executable entry point for the deployable AS process shell."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Sequence
from types import FrameType

from as_platform.ops.downscale_config import load_downscale_guard_config
from as_platform.runtime.active_calls import ActiveCallSource, resolve_instance_id
from as_platform.runtime.health import HealthServer, HealthServerConfig
from as_platform.shell import ProcessShell, ShellConfig
from as_platform.telemetry import BoundedQueueSink, default_sink
from as_platform.telemetry.metrics import CallMetrics, MetricsRegistry, emit_snapshot

_DEFAULT_DRAIN_TIMEOUT_SECONDS = 300.0
_DRAIN_TIMEOUT_EXIT_CODE = 1
_RUNTIME_ERROR_EXIT_CODE = 2
_METRICS_INTERVAL_SECONDS = 15.0


def build_shell(
    config: ShellConfig,
    active_calls: Callable[[], int],
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> ProcessShell:
    """Assemble the process shell from explicitly injected collaborators.

    Args:
        config: Draining and polling parameters.
        active_calls: Returns the current number of in-flight calls.
        sleep: Suspends draining between active-call checks.
        now: Returns monotonic seconds for the drain deadline.

    Returns:
        A shell that initially accepts new requests.
    """
    return ProcessShell(config=config, active_calls=active_calls, sleep=sleep, now=now)


def _parse_config(argv: Sequence[str] | None) -> tuple[ShellConfig, bool]:
    """Parse process-shell configuration from command-line arguments."""
    parser = argparse.ArgumentParser(description="Run the AS process shell.")
    parser.add_argument(
        "--drain-timeout-seconds",
        type=float,
        default=_DEFAULT_DRAIN_TIMEOUT_SECONDS,
        help="maximum time to wait for in-flight calls during termination",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=ShellConfig.poll_interval_seconds,
        help="delay between active-call checks while draining",
    )
    parser.add_argument(
        "--no-health-server",
        action="store_true",
        help="disable the HTTP health/metrics server (unit tests)",
    )
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    config = ShellConfig(
        drain_timeout_seconds=arguments.drain_timeout_seconds,
        poll_interval_seconds=arguments.poll_interval_seconds,
    )
    return config, arguments.no_health_server


def _optional_int_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    return int(raw)


def _start_metrics_loop(
    registry: MetricsRegistry,
    call_metrics: CallMetrics,
    active_calls: ActiveCallSource,
    instance_id: str,
    use_case: str,
    sink: BoundedQueueSink | object,
    stop: threading.Event,
) -> threading.Thread:
    def loop() -> None:
        while not stop.is_set():
            count = active_calls.count()
            call_metrics.set_active_calls(instance_id, use_case, count)
            if isinstance(sink, BoundedQueueSink):
                emit_snapshot(sink, registry)
            stop.wait(_METRICS_INTERVAL_SECONDS)

    thread = threading.Thread(target=loop, name="as-metrics-loop", daemon=True)
    thread.start()
    return thread


def main(argv: Sequence[str] | None = None) -> int:
    """Run the signal-aware process shell until termination.

    Exit code ``0`` means draining completed normally. A non-zero exit code means
    that draining timed out or the runtime raised an exception.

    Args:
        argv: Optional command-line arguments. ``None`` reads the process command
            line through :mod:`argparse`.

    Returns:
        ``0`` after a clean drain, ``1`` after a drain timeout, or ``2`` after a
        runtime exception.
    """
    config, disable_health = _parse_config(argv)
    guard = load_downscale_guard_config()
    logging.info(
        "downscale guard enabled=%s protect_above=%s",
        guard.enabled,
        guard.protect_when_active_calls_above,
    )

    shell_holder: list[ProcessShell] = []

    def is_terminating() -> bool:
        return not shell_holder[0].accepts_new_requests() if shell_holder else False

    call_source = ActiveCallSource(is_terminating=is_terminating, now=time.monotonic)
    shell = build_shell(
        config=config,
        active_calls=call_source.count,
        sleep=time.sleep,
        now=time.monotonic,
    )
    shell_holder.append(shell)

    instance_id = resolve_instance_id()
    use_case = os.environ.get("AS_USE_CASE", "unknown")
    registry = MetricsRegistry()
    call_metrics = CallMetrics(registry)

    telemetry_sink = default_sink()
    bounded_sink: BoundedQueueSink | None = None
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if otel_endpoint:
        bounded_sink = BoundedQueueSink(capacity=256)
        bounded_sink.start()

    health_server: HealthServer | None = None
    health_port = _optional_int_env("AS_HEALTH_PORT")
    if health_port is not None and not disable_health:
        health_server = HealthServer(
            HealthServerConfig(port=health_port),
            is_ready=shell.accepts_new_requests,
            metrics_registry=registry,
        )
        health_server.start()

    metrics_stop = threading.Event()
    metrics_thread = _start_metrics_loop(
        registry,
        call_metrics,
        call_source,
        instance_id,
        use_case,
        bounded_sink if bounded_sink is not None else telemetry_sink,
        metrics_stop,
    )

    def request_terminate(_signum: int, _frame: FrameType | None) -> None:
        shell.request_terminate()

    termination_signals = (signal.SIGTERM, signal.SIGINT)
    previous_handlers = {signum: signal.getsignal(signum) for signum in termination_signals}

    try:
        for signum in termination_signals:
            signal.signal(signum, request_terminate)

        while shell.accepts_new_requests():
            signal.pause()

        return 0 if shell.run_until_drained() else _DRAIN_TIMEOUT_EXIT_CODE
    except Exception:
        logging.exception("The AS process shell failed")
        return _RUNTIME_ERROR_EXIT_CODE
    finally:
        metrics_stop.set()
        metrics_thread.join(timeout=2.0)
        if bounded_sink is not None:
            bounded_sink.stop()
        if health_server is not None:
            health_server.stop()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
