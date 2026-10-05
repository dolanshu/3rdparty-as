"""Unit tests for D10 product checkpoint load hook (not native restore)."""

from __future__ import annotations

import pytest

from as_platform.sip.recovery import (
    NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED,
    CallStateRecovery,
)
from as_platform.sip.resip_recovery import load_resip_recovery_extension
from as_platform.state.call_checkpoint import (
    CallStateCheckpoint,
    CallStateCheckpointRepository,
    DialogLegCheckpoint,
)
from as_platform.state.in_memory import InMemoryStateStore

pytestmark = pytest.mark.unit


def _minimal_checkpoint(uas_call_id: str, uac_call_id: str) -> CallStateCheckpoint:
    leg_fields = {
        "local_tag": "local",
        "remote_tag": "remote",
        "local_uri": "sip:as@127.0.0.1",
        "remote_uri": "sip:peer@127.0.0.1",
        "remote_target": "sip:peer@127.0.0.1",
        "route_set": (),
        "local_cseq": 1,
        "remote_cseq": 1,
    }
    return CallStateCheckpoint(
        state="established",
        uas_leg=DialogLegCheckpoint(call_id=uas_call_id, **leg_fields),
        uac_leg=DialogLegCheckpoint(call_id=uac_call_id, **leg_fields),
    )


def test_on_process_start_restore_loads_repository_checkpoints() -> None:
    assert NATIVE_ON_PROCESS_START_RESTORE_IMPLEMENTED is True
    case = "translation"
    call_key = "uas-dialog@ims.example.net"
    store = InMemoryStateStore(now=lambda: 1.0)
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=3600,
        allowed_header_namespaces={},
    )
    checkpoint = _minimal_checkpoint(call_key, "uac-dialog@ims.example.net")
    repository.save(case=case, call_key=call_key, checkpoint=checkpoint)

    recovery = CallStateRecovery(repository)
    result = recovery.on_process_start_restore(case, (call_key, "missing-key"))

    assert len(result.loaded) == 1
    assert result.loaded[0].call_key == call_key
    assert result.loaded[0].checkpoint == checkpoint
    assert result.missing_call_keys == ("missing-key",)
    if load_resip_recovery_extension() is None:
        assert result.native_recovery_started is False
    else:
        assert result.native_recovery_started is True
        recovery.stop_native_recovery_sessions()


def test_on_process_start_restore_spawns_native_from_loaded_checkpoint() -> None:
    if load_resip_recovery_extension() is None:
        pytest.skip("platform _resip_recovery extension not built")

    case = "translation"
    call_key = "uas-dialog@ims.example.net"
    store = InMemoryStateStore(now=lambda: 1.0)
    repository = CallStateCheckpointRepository(
        store=store,
        ttl_seconds=3600,
        allowed_header_namespaces={},
    )
    checkpoint = _minimal_checkpoint(call_key, "uac-dialog@ims.example.net")
    repository.save(case=case, call_key=call_key, checkpoint=checkpoint)

    recovery = CallStateRecovery(repository)
    try:
        result = recovery.on_process_start_restore(case, (call_key,))
        assert result.native_recovery_started is True
        assert len(recovery._native_sessions) == 1
    finally:
        recovery.stop_native_recovery_sessions()
