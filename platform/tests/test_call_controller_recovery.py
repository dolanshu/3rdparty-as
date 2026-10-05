"""Unit tests: CallController restore and in-dialog BYE routing (M7.3)."""

from __future__ import annotations

import pytest

from as_platform.sip.call_controller import CallController, LegId
from as_platform.state.call_checkpoint import CallStateCheckpoint, DialogLegCheckpoint

pytestmark = pytest.mark.unit


def _checkpoint() -> CallStateCheckpoint:
    shared = {
        "local_tag": "as-local",
        "remote_tag": "peer-remote",
        "local_uri": "sip:as@127.0.0.1",
        "remote_uri": "sip:upstream@127.0.0.1",
        "remote_target": "sip:upstream@127.0.0.1",
        "route_set": (),
        "local_cseq": 2,
        "remote_cseq": 3,
    }
    return CallStateCheckpoint(
        state="established",
        uas_leg=DialogLegCheckpoint(call_id="uas-call@127.0.0.1", **shared),
        uac_leg=DialogLegCheckpoint(
            call_id="uac-call@127.0.0.1",
            local_tag="as-uac-local",
            remote_tag="peer-uac-remote",
            local_uri="sip:as@127.0.0.1",
            remote_uri="sip:downstream@127.0.0.1:5099",
            remote_target="sip:downstream@127.0.0.1:5099",
            route_set=(),
            local_cseq=4,
            remote_cseq=5,
        ),
    )


def test_restore_from_checkpoint_rebuilds_leg_map() -> None:
    controller = CallController()
    checkpoint = _checkpoint()
    controller.restore_from_checkpoint(checkpoint)
    assert controller.active_call_count() == 1
    correlation = controller.correlation_for_inbound(LegId(call_id=checkpoint.uas_leg.call_id))
    assert correlation is not None
    assert correlation.outbound is not None
    assert correlation.outbound.call_id == checkpoint.uac_leg.call_id


def test_route_in_dialog_bye_returns_downstream_target() -> None:
    controller = CallController()
    checkpoint = _checkpoint()
    controller.restore_from_checkpoint(checkpoint)
    target = controller.route_in_dialog_bye(checkpoint.uas_leg.call_id)
    assert target == checkpoint.uac_leg.remote_target
    assert controller.route_in_dialog_bye("unknown-call") is None
