"""Unit tests for the SIP boundary seam.

Acceptance: hld.md §1.2 (M2b lands seams and contracts only), §5 step 2
(translation carries no SIP concepts into the kernel) and step 4 (603 / 404),
plus ADR-0002 (``received_at`` is injected, never read).
"""

from __future__ import annotations

from typing import Protocol

import pytest

from as_platform.decision.decide import DecisionAction
from as_platform.sip.adapter import (
    STATUS_CONTINUE,
    STATUS_DECLINE,
    STATUS_NOT_FOUND,
    SipAdapter,
    SipRequestView,
    decision_to_status_code,
    to_decision_request,
)

pytestmark = pytest.mark.unit

RECEIVED_AT = 1_700_000_000.5


def _view() -> SipRequestView:
    return SipRequestView(
        method="INVITE",
        request_uri="sip:+8675512345678@as.example",
        call_id="call-1",
        calling_number="+8675500000000",
        called_number="+8675512345678",
        body=b"v=0\r\n",
    )


def test_to_decision_request_carries_the_numbers_and_the_call_id() -> None:
    """The boundary view is handed to the kernel field for field."""
    request = to_decision_request(_view(), RECEIVED_AT)

    assert request.call_id == "call-1"
    assert request.calling_number == "+8675500000000"
    assert request.called_number == "+8675512345678"


def test_to_decision_request_injects_received_at_verbatim() -> None:
    """The clock is the caller's: whatever is passed in is what the kernel sees."""
    for injected in (0.0, RECEIVED_AT, 1.0):
        assert to_decision_request(_view(), injected).received_at == injected


def test_decline_is_603() -> None:
    """REQ-F-7: a blocked call is answered 603 Decline (RFC 3261 §21.6.2)."""
    assert decision_to_status_code(DecisionAction.DECLINE) == STATUS_DECLINE == 603


def test_not_found_is_404() -> None:
    """REQ-F-6: no matching rule is answered 404 Not Found (RFC 3261 §21.4.5)."""
    assert decision_to_status_code(DecisionAction.NOT_FOUND) == STATUS_NOT_FOUND == 404


def test_forward_and_translate_continue() -> None:
    """Neither produces a terminal response; the call goes out on a leg."""
    assert decision_to_status_code(DecisionAction.FORWARD) == STATUS_CONTINUE
    assert decision_to_status_code(DecisionAction.TRANSLATE) == STATUS_CONTINUE
    assert STATUS_CONTINUE == 0


class _FakeAdapter:
    """A minimal stand-in for the stack binding; the shape is what is under test."""

    def parse(self, raw: bytes) -> SipRequestView | None:
        """Return a fixed view for any non-empty input, ``None`` otherwise."""
        if not raw:
            return None
        return _view()

    def respond(self, view: SipRequestView, status_code: int) -> bytes:
        """Render a response as ``<code> <call-id>``."""
        return f"{status_code} {view.call_id}".encode()

    def forward(self, view: SipRequestView, target: str) -> bytes:
        """Render an outbound leg request as ``<method> <target>``."""
        return f"{view.method} {target}".encode()


def _use(adapter: SipAdapter) -> SipRequestView | None:
    """A consumer written against the Protocol; any conforming object works."""
    return adapter.parse(b"INVITE sip:+8675512345678@as.example SIP/2.0\r\n")


def test_adapter_is_a_protocol() -> None:
    """The seam is structural: it declares members, it does not implement them."""
    assert Protocol in SipAdapter.__mro__


def test_a_minimal_implementation_is_usable_as_a_sip_adapter() -> None:
    """Duck typing is enough: the fake satisfies the Protocol without inheriting it."""
    parsed = _use(_FakeAdapter())

    assert parsed is not None
    assert parsed.call_id == "call-1"


def test_malformed_input_parses_to_none_so_the_caller_discards() -> None:
    """A message we cannot understand is not a call and must not reach decide()."""
    assert _FakeAdapter().parse(b"") is None


def test_fake_adapter_builds_responses_and_outbound_legs() -> None:
    """The two remaining members round-trip through the seam's own view."""
    adapter = _FakeAdapter()
    view = _view()

    assert adapter.respond(view, STATUS_DECLINE) == b"603 call-1"
    assert adapter.forward(view, "sip:return-uas@as.example") == b"INVITE sip:return-uas@as.example"
