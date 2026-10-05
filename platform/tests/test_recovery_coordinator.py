"""Unit tests: non-blocking recovery coordinator (M7.2)."""

from __future__ import annotations

import threading
import time

import pytest

from as_platform.sip.recovery import CallStateRecovery
from as_platform.sip.recovery_coordinator import RecoveryCoordinator
from as_platform.state.call_checkpoint import (
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    DialogLegCheckpoint,
)
from as_platform.state.in_memory import InMemoryStateStore

pytestmark = pytest.mark.unit


class SlowRepository(CallStateCheckpointRepository):
    """Repository that sleeps in ``load`` to prove work stays off the SIP thread."""

    def __init__(self, store: InMemoryStateStore, ttl_seconds: int) -> None:
        super().__init__(store=store, ttl_seconds=ttl_seconds, allowed_header_namespaces={})
        self.load_started = threading.Event()
        self.allow_load = threading.Event()

    def load(self, case: str, call_key: str) -> CallStateCheckpoint | None:
        self.load_started.set()
        assert not self.allow_load.is_set()
        self.allow_load.wait(timeout=2.0)
        return super().load(case=case, call_key=call_key)


def _minimal_checkpoint() -> CallStateCheckpoint:
    leg = {
        "local_tag": "l",
        "remote_tag": "r",
        "local_uri": "sip:a@127.0.0.1",
        "remote_uri": "sip:b@127.0.0.1",
        "remote_target": "sip:b@127.0.0.1",
        "route_set": (),
        "local_cseq": 1,
        "remote_cseq": 1,
    }
    return CallStateCheckpoint(
        state="established",
        uas_leg=DialogLegCheckpoint(call_id="uas@127.0.0.1", **leg),
        uac_leg=DialogLegCheckpoint(call_id="uac@127.0.0.1", **leg),
    )


def test_schedule_restore_invokes_callback_on_worker_thread() -> None:
    store = InMemoryStateStore(now=lambda: 1.0)
    repository = SlowRepository(store=store, ttl_seconds=60)
    checkpoint = _minimal_checkpoint()
    repository.save(case="translation", call_key="uas@127.0.0.1", checkpoint=checkpoint)
    coordinator = RecoveryCoordinator(CallStateRecovery(repository))
    callback_thread = threading.Event()
    results: list[object] = []

    def on_restored(result: object) -> None:
        callback_thread.set()
        results.append(result)

    coordinator.schedule_restore("translation", ("uas@127.0.0.1",), on_restored)
    assert repository.load_started.wait(timeout=2.0)
    time.sleep(0.05)
    assert not callback_thread.is_set()
    repository.allow_load.set()
    assert callback_thread.wait(timeout=2.0)
    assert len(results) == 1
    coordinator.shutdown()
