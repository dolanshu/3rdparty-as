"""D10 subprocess child: ``SipStackService`` accept-all until SIGTERM.

Used by ``test_d10_process_restart_integration.py``. Writes the runtime UDP
port to ``AS_D10_PORT_FILE`` after start. When ``AS_D10_RECOVERY_PORT_FILE`` is
set and native restore completes, writes the first RecoveryTU listen port there.
"""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

from as_platform.runtime.active_calls import ActiveCallSource
from as_platform.runtime.sip_stack_service import SipStackService
from as_platform.sip.recovery import ProcessStartRestoreResult
from as_platform.sip.resip_recovery import RecoveryStackSession

_STOP = False


def _request_stop(_signum: int, _frame: object) -> None:
    global _STOP
    _STOP = True


def _pump_recovery_sessions(service: SipStackService) -> None:
    for session in service._recovery._native_sessions:
        if isinstance(session, RecoveryStackSession):
            try:
                session.process(25)
                status = session.status()
                if status["downstream_200"] and not status["upstream_200_queued"]:
                    session.send_upstream_200()
            except RuntimeError:
                continue


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    port_file = os.environ.get("AS_D10_PORT_FILE", "").strip()
    recovery_port_file = os.environ.get("AS_D10_RECOVERY_PORT_FILE", "").strip()

    active = ActiveCallSource(is_terminating=lambda: _STOP, now=time.monotonic)
    service = SipStackService.from_env(active)
    if service is None:
        logging.error("AS_ENABLE_SIP_RUNTIME is not set")
        return 2

    if recovery_port_file:
        original = service._handle_restore_result

        def _wrapped(result: ProcessStartRestoreResult) -> None:
            original(result)
            if result.native_recovery_started:
                sessions = service._recovery._native_sessions
                if sessions and isinstance(sessions[0], RecoveryStackSession):
                    Path(recovery_port_file).write_text(
                        str(sessions[0].listen_port), encoding="ascii"
                    )

        service._handle_restore_result = _wrapped  # type: ignore[method-assign]

    try:
        service.start()
    except Exception:
        logging.exception("failed to start SipStackService")
        return 2

    if port_file:
        Path(port_file).write_text(str(service.listen_port), encoding="ascii")

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    while not _STOP:
        _pump_recovery_sessions(service)
        time.sleep(0.05)

    service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
