"""Contract tests: the derived baselines of docs/plan.md §4.1, as assertions.

S5 / S6 / S7a / S8 are not captured as baselines of their own; they are derived
from ``S1-basic-call``. Until now that decision was a sentence in a plan. These
tests turn it into executable evidence by reading the S1 capture and asserting
what the two legs of the call must satisfy:

* REQ-F-2 - the two legs carry different Call-IDs, and one leg keeps its
  Call-ID for the whole dialog (RFC 3261 §8.1.1.4).
* REQ-F-3 - the Request-URI is rewritten when the call crosses the B2BUA.
* REQ-F-4 - the SDP body crosses the B2BUA byte for byte.
* REQ-F-5 - Route and Record-Route are honoured.

The capture is read only. A header field the S1 scenario never constructs is
reported as a skip, never as a pass: an unproven assertion is not a proven one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from as_simulators.sip_message import (
    SipMessage,
    call_id,
    header,
    headers_all,
    is_request,
    parse_message,
    request_uri,
)

pytestmark = pytest.mark.contract

BASELINE_NAME: Final = "S1-basic-call"
EXPECTED_MESSAGE_COUNT: Final = 14

# Message files of the capture. The file name says direction and peer:
# "in-" is towards the AS, "out-" leaves it, "-trunk" is the calling (office)
# side, "-core" is the called (mobile) side.
INGRESS_INVITE: Final = "01-in-invite-trunk.txt"
EGRESS_INVITE: Final = "03-out-invite-core.txt"
# The BYE of the trunk-facing leg: sent by the AS towards the trunk.
INGRESS_BYE: Final = "13-out-bye-trunk.txt"
# The BYE of the core-facing leg: sent by the core towards the AS.
EGRESS_BYE: Final = "11-in-bye-core.txt"
# The 200 OK that comes back from the upstream (core) side...
UPSTREAM_200: Final = "07-in-200-core.txt"
# ...and the 200 OK the AS sends back on the trunk-facing side.
DOWNSTREAM_200: Final = "09-out-200-trunk.txt"

# China country code, and the national trunk prefix that replaces it.
COUNTRY_CODE: Final = "86"
NATIONAL_PREFIX: Final = "0"


def _repository_root() -> Path:
    """Return the workspace root, whichever directory the run started from.

    The root is the only ancestor that holds both the workspace manifest and
    the ``testbed/`` tree, so the walk stops there and nowhere else.
    """
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "testbed").is_dir():
            return candidate
    return here.parents[3]


def _baseline_dir() -> Path:
    """Return the directory holding the S1 capture."""
    return _repository_root() / "testbed" / "contracts" / "sip-baseline" / BASELINE_NAME


@pytest.fixture(scope="module")
def messages() -> dict[str, SipMessage]:
    """Every message of the baseline, parsed and keyed by file name."""
    directory = _baseline_dir()
    if not directory.is_dir():
        pytest.skip(f"baseline {BASELINE_NAME} is not captured at {directory}")
    return {path.name: parse_message(path.read_bytes()) for path in sorted(directory.glob("*.txt"))}


def _require(messages: dict[str, SipMessage], name: str) -> SipMessage:
    """Return one message of the baseline, or skip if it was never captured."""
    if name not in messages:
        pytest.skip(f"{BASELINE_NAME} does not carry {name}")
    return messages[name]


def _uri_user(uri: str) -> str:
    """Return the user part of a SIP or SIPS URI."""
    _, _, rest = uri.partition(":")
    return rest.split("@", 1)[0]


def _uri_host_port(uri: str) -> str:
    """Return the host[:port] part of a SIP or SIPS URI."""
    return uri.split("@", 1)[1] if "@" in uri else uri


def _route_target(value: str) -> str:
    """Return the host[:port] a Route or Record-Route value points at."""
    stripped = value.strip().strip("<>")
    _, _, rest = stripped.partition(":")
    return rest.split(";", 1)[0]


def _subscriber_digits(uri: str) -> str:
    """Return the subscriber digits of a Request-URI in comparable form.

    The trunk side carries the E.164 form (``+8613800138000``) and the core side
    carries the national form (``013800138000``); rule R-MOB-CM-40 translates
    between the two. Dropping the leading ``+`` with the country code on one
    side and the national trunk prefix on the other leaves the same digits,
    which is the invariant worth asserting. The user parts themselves are not
    byte-identical and are not meant to be.
    """
    user = _uri_user(uri)
    if user.startswith("+"):
        return user[1:].removeprefix(COUNTRY_CODE)
    return user.lstrip(NATIONAL_PREFIX)


def test_baseline_carries_every_message(messages: dict[str, SipMessage]) -> None:
    """The S1 capture is the whole call: fourteen messages, no more, no less."""
    assert len(messages) == EXPECTED_MESSAGE_COUNT, (
        f"{BASELINE_NAME} carries {len(messages)} messages, expected {EXPECTED_MESSAGE_COUNT}"
    )


def test_every_captured_message_parses(messages: dict[str, SipMessage]) -> None:
    """No message of the capture is rejected by the parser."""
    assert messages, "the capture holds no message"
    for name, msg in messages.items():
        assert msg.start_line, f"{name} parsed to an empty start line"
        assert is_request(msg) or msg.start_line.startswith("SIP/"), (
            f"{name}: start line is neither a request nor a status line: {msg.start_line!r}"
        )


def test_req_f2_call_id_differs_between_the_two_legs(messages: dict[str, SipMessage]) -> None:
    """REQ-F-2: the B2BUA gives the second leg a Call-ID of its own."""
    ingress = call_id(_require(messages, INGRESS_INVITE))
    egress = call_id(_require(messages, EGRESS_INVITE))
    assert ingress is not None, f"{INGRESS_INVITE} carries no Call-ID"
    assert egress is not None, f"{EGRESS_INVITE} carries no Call-ID"
    assert ingress != egress, f"both legs carry the Call-ID {ingress}; a B2BUA must start a new one"


def test_req_f2_call_id_is_stable_within_one_dialog(messages: dict[str, SipMessage]) -> None:
    """REQ-F-2: a leg keeps its Call-ID from the INVITE to the BYE.

    RFC 3261 §8.1.1.4 fixes the Call-ID for the whole dialog, and the PRD review
    (finding A2) concluded the same for this AS: a BYE that changed it would
    land in a dialog the peer does not know.
    """
    ingress_invite = call_id(_require(messages, INGRESS_INVITE))
    ingress_bye = call_id(_require(messages, INGRESS_BYE))
    assert ingress_invite is not None, f"{INGRESS_INVITE} carries no Call-ID"
    assert ingress_bye is not None, f"{INGRESS_BYE} carries no Call-ID"
    assert ingress_invite == ingress_bye, (
        f"the trunk leg changed its Call-ID: {ingress_invite} then {ingress_bye}"
    )

    egress_invite = call_id(_require(messages, EGRESS_INVITE))
    egress_bye = call_id(_require(messages, EGRESS_BYE))
    assert egress_invite is not None, f"{EGRESS_INVITE} carries no Call-ID"
    assert egress_bye is not None, f"{EGRESS_BYE} carries no Call-ID"
    assert egress_invite == egress_bye, (
        f"the core leg changed its Call-ID: {egress_invite} then {egress_bye}"
    )


def test_req_f3_request_uri_target_is_rewritten(messages: dict[str, SipMessage]) -> None:
    """REQ-F-3: the two legs of the call do not share a target host and port."""
    ingress_uri = request_uri(_require(messages, INGRESS_INVITE))
    egress_uri = request_uri(_require(messages, EGRESS_INVITE))
    assert ingress_uri is not None, f"{INGRESS_INVITE} carries no Request-URI"
    assert egress_uri is not None, f"{EGRESS_INVITE} carries no Request-URI"
    assert _uri_host_port(ingress_uri) != _uri_host_port(egress_uri), (
        f"both legs target {_uri_host_port(ingress_uri)}; the second leg must be re-targeted"
    )


def test_req_f3_request_uri_keeps_the_same_subscriber(messages: dict[str, SipMessage]) -> None:
    """REQ-F-3: rewriting the Request-URI keeps the called subscriber.

    The user part is translated, not copied: E.164 ``+8613800138000`` becomes
    the national ``013800138000`` under R-MOB-CM-40. What must survive the
    rewrite is the subscriber, so the two forms are normalised before they are
    compared.
    """
    ingress_uri = request_uri(_require(messages, INGRESS_INVITE))
    egress_uri = request_uri(_require(messages, EGRESS_INVITE))
    assert ingress_uri is not None, f"{INGRESS_INVITE} carries no Request-URI"
    assert egress_uri is not None, f"{EGRESS_INVITE} carries no Request-URI"
    assert _subscriber_digits(ingress_uri) == _subscriber_digits(egress_uri), (
        f"the rewrite lost the subscriber: {ingress_uri} became {egress_uri}"
    )


def test_req_f4_invite_body_crosses_unchanged(messages: dict[str, SipMessage]) -> None:
    """REQ-F-4: the SDP offer of the INVITE is passed through byte for byte."""
    ingress_body = _require(messages, INGRESS_INVITE).body
    egress_body = _require(messages, EGRESS_INVITE).body
    if not ingress_body or not egress_body:
        pytest.skip(
            f"{BASELINE_NAME} does not carry an SDP body on both INVITEs "
            f"({len(ingress_body)} and {len(egress_body)} bytes); nothing to compare"
        )
    assert ingress_body == egress_body, (
        "the SDP offer was rewritten on the way through: "
        f"{len(ingress_body)} bytes in, {len(egress_body)} bytes out"
    )


def test_req_f4_answer_body_crosses_unchanged(messages: dict[str, SipMessage]) -> None:
    """REQ-F-4: the SDP answer of the 200 OK is passed through byte for byte."""
    upstream_body = _require(messages, UPSTREAM_200).body
    downstream_body = _require(messages, DOWNSTREAM_200).body
    if not upstream_body or not downstream_body:
        pytest.skip(
            f"{BASELINE_NAME} does not carry an SDP body on both 200 OKs "
            f"({len(upstream_body)} and {len(downstream_body)} bytes); nothing to compare"
        )
    assert upstream_body == downstream_body, (
        "the SDP answer was rewritten on the way back: "
        f"{len(upstream_body)} bytes in, {len(downstream_body)} bytes out"
    )


def test_req_f5_ingress_invite_carries_a_route(messages: dict[str, SipMessage]) -> None:
    """REQ-F-5: the scenario the S8 assertions are derived from has a Route."""
    route = headers_all(_require(messages, INGRESS_INVITE), "Route")
    assert route, f"{INGRESS_INVITE} carries no Route header; the S8 derivation would be vacuous"


def test_req_f5_egress_invite_carries_a_route(messages: dict[str, SipMessage]) -> None:
    """REQ-F-5: the egress INVITE carries a Route header too."""
    route = headers_all(_require(messages, EGRESS_INVITE), "Route")
    if not route:
        pytest.skip(
            f"{BASELINE_NAME} constructs no Route header on {EGRESS_INVITE}: the AS sends "
            "the second leg straight to its Request-URI instead of through a next hop. "
            "A dedicated M2 probe capture is needed before this can be asserted."
        )
    assert route


def test_req_f5_route_next_hop_becomes_the_egress_target(messages: dict[str, SipMessage]) -> None:
    """REQ-F-5: where the ingress Route points is where the egress INVITE goes.

    Routing through the Route next hop is observable without a Route header on
    the second leg: the host and port of that hop become the host and port of
    the rewritten Request-URI.
    """
    ingress = _require(messages, INGRESS_INVITE)
    route = header(ingress, "Route")
    if route is None:
        pytest.skip(
            f"{BASELINE_NAME} constructs no Route header on {INGRESS_INVITE}; "
            "a dedicated M2 probe capture is needed before this can be asserted."
        )
    egress_uri = request_uri(_require(messages, EGRESS_INVITE))
    assert egress_uri is not None, f"{EGRESS_INVITE} carries no Request-URI"
    assert _route_target(route) == _uri_host_port(egress_uri), (
        f"the egress INVITE went to {_uri_host_port(egress_uri)} instead of the "
        f"Route next hop {_route_target(route)}"
    )


def test_req_f5_record_route_reaches_the_upstream_side(messages: dict[str, SipMessage]) -> None:
    """REQ-F-5: a Record-Route of a response is present on the upstream side."""
    carriers = [name for name, msg in messages.items() if headers_all(msg, "Record-Route")]
    if not carriers:
        pytest.skip(
            f"{BASELINE_NAME} constructs no Record-Route header in any of its "
            f"{len(messages)} messages; a dedicated M2 probe capture is needed "
            "before this can be asserted."
        )
    assert any("core" in name for name in carriers), (
        f"Record-Route appears only on {sorted(carriers)}, never on the upstream side"
    )
