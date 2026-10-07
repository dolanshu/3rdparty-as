"""Contract tests: native ``RESIP_RUNTIME_*`` log line field contract (M8 A-2 F8).

Each case feeds a representative cout/cerr line copied from
``platform/native/resip_runtime/runtime_module.cxx`` and asserts the parsed
field names/values. A C++ format drift (renamed event or key) fails these
tests by design.
"""

from __future__ import annotations

import pytest

from as_platform.sip.resip_runtime_log_contract import (
    ResipRuntimeLogEvent,
    is_resip_runtime_log_line,
    parse_resip_runtime_log_line,
)

pytestmark = pytest.mark.contract


def test_listening_udp_line_parses_ports() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_LISTENING address=127.0.0.1 advertised=127.0.0.1 udp_port=5060"
    )
    assert event is not None
    assert event.event == "RESIP_RUNTIME_LISTENING"
    assert event.fields == {
        "address": "127.0.0.1",
        "advertised": "127.0.0.1",
        "udp_port": "5060",
    }


def test_listening_tls_line_parses_tls_port() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_LISTENING address=127.0.0.1 advertised=127.0.0.1 tls_port=5061"
    )
    assert event is not None
    assert event.event == "RESIP_RUNTIME_LISTENING"
    assert event.fields["tls_port"] == "5061"


def test_uac_invite_sent_parses_correlation_ids() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_UAC_INVITE_SENT outgoing_call_id=out-1@127.0.0.1"
        " inbound_call_id=in-1@127.0.0.1 route_uri=sip:downstream@127.0.0.1:5070"
    )
    assert event is not None
    assert event.event == "RESIP_RUNTIME_UAC_INVITE_SENT"
    assert event.fields["outgoing_call_id"] == "out-1@127.0.0.1"
    assert event.fields["inbound_call_id"] == "in-1@127.0.0.1"
    assert event.fields["route_uri"] == "sip:downstream@127.0.0.1:5070"


def test_uac_new_session_parses_outgoing_call_id() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_UAC_NEW_SESSION outgoing_call_id=out-1@127.0.0.1"
    )
    assert event is not None
    assert event.event == "RESIP_RUNTIME_UAC_NEW_SESSION"
    assert event.fields == {"outgoing_call_id": "out-1@127.0.0.1"}


def test_uac_failure_parses_status() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_UAC_FAILURE outgoing_call_id=out-1@127.0.0.1 status=486"
    )
    assert event is not None
    assert event.fields["outgoing_call_id"] == "out-1@127.0.0.1"
    assert event.fields["status"] == "486"


def test_uas_failure_mapped_parses_status_pair() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_UAS_FAILURE_MAPPED outgoing_call_id=out-1@127.0.0.1"
        " downstream_status=486 upstream_status=486"
    )
    assert event is not None
    assert event.event == "RESIP_RUNTIME_UAS_FAILURE_MAPPED"
    assert event.fields["downstream_status"] == "486"
    assert event.fields["upstream_status"] == "486"


def test_outbound_cancel_forward_parses_inbound_call_id() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD inbound_call_id=in-1@127.0.0.1"
    )
    assert event is not None
    assert event.fields == {"inbound_call_id": "in-1@127.0.0.1"}


def test_uas_answer_relayed_parses_outgoing_call_id() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_UAS_ANSWER_RELAYED outgoing_call_id=out-1@127.0.0.1"
    )
    assert event is not None
    assert event.event == "RESIP_RUNTIME_UAS_ANSWER_RELAYED"
    assert event.fields == {"outgoing_call_id": "out-1@127.0.0.1"}


def test_callback_error_without_equals_fails_closed() -> None:
    # ``RESIP_RUNTIME_CALLBACK_ERROR message=<err>`` values may contain spaces;
    # the contract fails closed (None) rather than guessing field boundaries.
    assert (
        parse_resip_runtime_log_line(
            "RESIP_RUNTIME_CALLBACK_ERROR message=Python callback raised an exception"
        )
        is None
    )


def test_error_events_map_to_error_level() -> None:
    event = parse_resip_runtime_log_line(
        "RESIP_RUNTIME_UAC_CORRELATION_MISS outgoing_call_id=out-9@127.0.0.1"
    )
    assert event is not None
    assert event.to_nf13_fields()["level"] == "error"
    assert event.to_nf13_fields()["call_id"] == "out-9@127.0.0.1"


def test_nf13_mapping_prefers_outgoing_call_id() -> None:
    event = ResipRuntimeLogEvent(
        event="RESIP_RUNTIME_UAC_INVITE_SENT",
        fields={"outgoing_call_id": "out-1", "inbound_call_id": "in-1"},
    )
    nf13 = event.to_nf13_fields()
    assert nf13["call_id"] == "out-1"
    assert nf13["trace_id"] == "out-1"
    assert nf13["direction"] == "outbound"
    assert nf13["method"] == "INVITE"
    assert nf13["timestamp"] is None


def test_nf13_mapping_cancel_is_inbound() -> None:
    event = ResipRuntimeLogEvent(
        event="RESIP_RUNTIME_OUTBOUND_CANCEL_FORWARD",
        fields={"inbound_call_id": "in-1"},
    )
    nf13 = event.to_nf13_fields()
    assert nf13["call_id"] == "in-1"
    assert nf13["direction"] == "inbound"
    assert nf13["method"] == "CANCEL"


def test_non_runtime_lines_are_ignored() -> None:
    assert parse_resip_runtime_log_line("") is None
    assert parse_resip_runtime_log_line("some other log line") is None
    assert parse_resip_runtime_log_line("RESIP_RUNTIME_UNKNOWN_EVENT foo=1") is None
    assert not is_resip_runtime_log_line("INFO unrelated")
    reload_event = parse_resip_runtime_log_line("RESIP_RUNTIME_RELOAD_CERTIFICATES invoked")
    assert reload_event is not None
    assert reload_event.fields == {"detail": "invoked"}
