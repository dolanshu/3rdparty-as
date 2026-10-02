from __future__ import annotations

import socket
import sys
import threading
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = Path("/home/shudong/project/3rdparty-as")
sys.path.insert(0, str(ROOT / "build"))
sys.path.insert(0, str(REPO / "platform" / "src"))

import _resip_dum
from as_platform.decision import DecisionAction, DecisionRequest, RuleSet, decide


def select_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def make_invite(server_port: int, caller_port: int, call_id: str) -> bytes:
    branch = "z9hG4bK-" + uuid.uuid4().hex
    lines = (
        f"INVITE sip:+15558675309@127.0.0.1:{server_port} SIP/2.0",
        f"Via: SIP/2.0/UDP 127.0.0.1:{caller_port};branch={branch};rport",
        "Max-Forwards: 70",
        "From: <sip:+15551230001@127.0.0.1>;tag=as-slice-caller",
        "To: <sip:+15558675309@127.0.0.1>",
        f"Call-ID: {call_id}",
        "CSeq: 1 INVITE",
        f"Contact: <sip:+15551230001@127.0.0.1:{caller_port}>",
        "Content-Length: 0",
        "",
        "",
    )
    return "\r\n".join(lines).encode("ascii")


def receive_final_response(peer: socket.socket) -> tuple[bytes, tuple[str, int]]:
    peer.settimeout(5.0)
    while True:
        response, address = peer.recvfrom(65535)
        status_line = response.split(b"\r\n", 1)[0]
        print(
            "SIP_PEER_RESPONSE "
            f"status_line={status_line.decode('ascii', errors='replace')} "
            f"from={address[0]}:{address[1]}",
            flush=True,
        )
        fields = status_line.split()
        if len(fields) >= 2 and fields[1].isdigit() and int(fields[1]) >= 200:
            return response, address


def run_case(case: str) -> None:
    port = select_loopback_port()
    call_id = f"{case}-{uuid.uuid4()}@127.0.0.1"
    caller_thread_id = threading.get_native_id()

    def policy_callback(
        received_call_id: str, calling_number: str, called_number: str
    ) -> int:
        request = DecisionRequest(
            call_id=received_call_id,
            calling_number=calling_number,
            called_number=called_number,
            received_at=0.0,
        )
        decision = decide(request, RuleSet(rules=()))
        print(
            "PYTHON_POLICY_DECISION "
            f"action={decision.action.value} call_id={received_call_id} "
            f"calling={calling_number} called={called_number}",
            flush=True,
        )
        if case == "exception":
            raise RuntimeError("intentional callback failure")
        if decision.action is DecisionAction.NOT_FOUND:
            return 404
        raise AssertionError(f"unexpected decision action: {decision.action}")

    peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    peer.bind(("127.0.0.1", 0))
    caller_port = peer.getsockname()[1]
    server = None
    markers = None
    final_response = b""
    response_address = ("", 0)

    try:
        server = _resip_dum.start_uas(port, policy_callback)
        peer.sendto(make_invite(port, caller_port, call_id), ("127.0.0.1", port))
        final_response, response_address = receive_final_response(peer)
    finally:
        if server is not None:
            markers = _resip_dum.stop_and_join(server)
        peer.close()

    assert markers is not None
    status_line = final_response.split(b"\r\n", 1)[0].decode("ascii")
    status_code = int(status_line.split()[1])
    expected_status = 500 if case == "exception" else 404
    assert status_code == expected_status, (status_line, expected_status)
    assert response_address == ("127.0.0.1", port), response_address
    assert call_id.encode("ascii") in final_response
    assert b"CSeq: 1 INVITE" in final_response
    assert markers["callback_ran"] is True, markers
    assert markers["response_issued"] is True, markers
    assert markers["response_status"] == expected_status, markers
    assert markers["call_id"] == call_id, markers
    assert markers["calling_number"] == "+15551230001", markers
    assert markers["request_user"] == "+15558675309", markers
    assert markers["event_loop_thread_id"] == markers["callback_thread_id"], markers
    assert markers["event_loop_thread_id"] != caller_thread_id, markers

    if case == "exception":
        assert markers["callback_exception"] is True, markers
        assert "intentional callback failure" in markers["callback_error"], markers
    else:
        assert markers["callback_exception"] is False, markers
        assert markers["callback_error"] == "", markers

    print(
        "CASE_PASS "
        f"case={case} status={status_code} port={port} "
        f"python_caller_tid={caller_thread_id} "
        f"event_loop_tid={markers['event_loop_thread_id']} "
        f"callback_tid={markers['callback_thread_id']} "
        f"callback_ran={markers['callback_ran']} "
        f"response_issued={markers['response_issued']} "
        f"callback_error={markers['callback_error']!r}",
        flush=True,
    )


def main() -> None:
    run_case("policy")
    run_case("exception")
    print("INTEGRATION_PASS cases=2", flush=True)


if __name__ == "__main__":
    main()