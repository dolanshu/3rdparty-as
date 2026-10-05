"""D10 product recovery hook: load Redis checkpoints outside SIP callbacks.

Matches the testbed ``d10-recovery`` Phase B pattern:
``CallStateCheckpointRepository.load(case, call_key)`` after process restart.

Product RecoveryTU lives in :mod:`as_platform.sip.resip_recovery` when the native
extension is built. This module keeps the non-blocking Python load contract.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from as_platform.state.call_checkpoint import CallStateCheckpoint, CallStateCheckpointRepository


def _native_recovery_built() -> bool:
    from as_platform.sip.resip_recovery import load_resip_recovery_extension

    return load_resip_recovery_extension() is not None


def _test_only_checkpoint_file() -> Path | None:
    """Optional native adapter path (tests only; not production process shell)."""
    raw = os.environ.get("AS_RESIP_RECOVERY_CHECKPOINT_FILE")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


# ``platform -m as_platform`` with ``AS_ENABLE_SIP_RUNTIME=1`` schedules Redis/in-memory
# restore via :class:`~as_platform.runtime.sip_stack_service.SipStackService`, which calls
# :meth:`CallStateRecovery.on_process_start_restore` and starts ``RecoveryStackSession`` per
# loaded checkpoint when ``_resip_recovery`` is built.
NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED = True


@dataclass(frozen=True, slots=True)
class LoadedCallCheckpoint:
    """One durable checkpoint keyed the same way as the testbed orchestrator."""

    case: str
    call_key: str
    checkpoint: CallStateCheckpoint


@dataclass(frozen=True, slots=True)
class ProcessStartRestoreResult:
    """Outcome of loading checkpoints at process start."""

    loaded: tuple[LoadedCallCheckpoint, ...]
    missing_call_keys: tuple[str, ...]
    native_recovery_started: bool = False


class CallStateRecovery:
    """Load established-call checkpoints for post-restart controller/DUM wiring."""

    def __init__(self, repository: CallStateCheckpointRepository) -> None:
        """Attach a typed checkpoint repository (Redis or in-memory in tests)."""
        self._repository = repository
        self._native_sessions: list[object] = []
        self._native_adapter_dirs: list[Path] = []

    def stop_native_recovery_sessions(self) -> None:
        """Stop any ``RecoveryStackSession`` instances started during restore."""
        from as_platform.sip.resip_recovery import RecoveryStackSession

        for session in self._native_sessions:
            if isinstance(session, RecoveryStackSession):
                session.stop()
        self._native_sessions.clear()
        for adapter_dir in self._native_adapter_dirs:
            shutil.rmtree(adapter_dir, ignore_errors=True)
        self._native_adapter_dirs.clear()

    def _start_native_for_loaded(self, loaded: tuple[LoadedCallCheckpoint, ...]) -> bool:
        if not loaded or not _native_recovery_built():
            return False
        from as_platform.sip.resip_recovery import RecoveryStackSession, write_native_adapter

        started = False
        for item in loaded:
            adapter_dir = Path(tempfile.mkdtemp(prefix="as-recovery-adapter-"))
            adapter_path = adapter_dir / "checkpoint.fields"
            write_native_adapter(adapter_path, item.checkpoint)
            session = RecoveryStackSession()
            try:
                session.start_from_adapter_file(adapter_path)
            except (OSError, RuntimeError):
                session.stop()
                shutil.rmtree(adapter_dir, ignore_errors=True)
            else:
                self._native_sessions.append(session)
                self._native_adapter_dirs.append(adapter_dir)
                started = True
        return started

    def on_process_start_restore(
        self,
        case: str,
        call_keys: tuple[str, ...],
    ) -> ProcessStartRestoreResult:
        """Load checkpoints for the given call keys (non-blocking; no Redis in SIP callbacks).

        This mirrors ``orchestrate.py`` Phase B sourcing
        ``PHASE_B_CHECKPOINT_SOURCE=CallStateCheckpointRepository.load``.

        When ``_resip_recovery`` is built, starts a
        :class:`~as_platform.sip.resip_recovery.RecoveryStackSession` per loaded checkpoint
        (adapter file written under a temp directory). The optional
        ``AS_RESIP_RECOVERY_CHECKPOINT_FILE`` env hook remains for narrow tests.

        Rehydrating DUM sessions beyond RecoveryTU startup is still limited to engineering
        slices; full D10 maintainer acceptance remains open.
        """
        loaded: list[LoadedCallCheckpoint] = []
        missing: list[str] = []
        for call_key in call_keys:
            checkpoint = self._repository.load(case=case, call_key=call_key)
            if checkpoint is None:
                missing.append(call_key)
                continue
            loaded.append(LoadedCallCheckpoint(case=case, call_key=call_key, checkpoint=checkpoint))

        native_started = self._start_native_for_loaded(tuple(loaded))

        adapter_path = _test_only_checkpoint_file()
        if adapter_path is not None and _native_recovery_built() and not native_started:
            from as_platform.sip.resip_recovery import RecoveryStackSession

            session = RecoveryStackSession()
            try:
                session.start_from_adapter_file(adapter_path)
            except (OSError, RuntimeError):
                session.stop()
            else:
                self._native_sessions.append(session)
                native_started = True

        return ProcessStartRestoreResult(
            loaded=tuple(loaded),
            missing_call_keys=tuple(missing),
            native_recovery_started=native_started,
        )
