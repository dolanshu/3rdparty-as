"""The SIP boundary seam: what the kernel sees of SIP, and nothing more.

hld.md §5 step 2 is explicit about the translation: the adapter turns a SIP
message into a :class:`DecisionRequest`, a kernel data structure that carries
**no SIP concepts** --- no headers, no dialog, no transaction. That is what lets
``decide()`` stay a pure function that has never heard of SIP (AGENT.md §5).

This module defines the seam only. There is no parser, no socket and no stack
here: the implementation is supplied by the M2b stack binding, reSIProcate per
ADR-0019, and the kernel depends on nothing but the :class:`SipAdapter`
Protocol below. hld.md §1.2 fixes the reason: binding a C++ stack is its own
work item, and the kernel must first be testable without one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from as_platform.decision.decide import DecisionAction, DecisionRequest

# RFC 3261 status codes the kernel decisions map onto (hld.md §5 step 4).
STATUS_DECLINE = 603  # RFC 3261 §21.6.2 --- REQ-F-7
STATUS_NOT_FOUND = 404  # RFC 3261 §21.4.5 --- REQ-F-6

#: Returned for FORWARD and TRANSLATE: there is no terminal response to send,
#: the call continues on an outbound leg.
STATUS_CONTINUE = 0


@dataclass(frozen=True)
class SipRequestView:
    """What the kernel is allowed to know about an inbound SIP request.

    Deliberately smaller than a SIP message: it is the boundary view, not the
    wire format. Anything the kernel would need a header for does not belong
    here --- it belongs in the stack binding.

    Attributes:
        method: The SIP method, for example ``INVITE``.
        request_uri: The Request-URI as received.
        call_id: The Call-ID; the kernel keys state and traces on it.
        calling_number: The calling party number.
        called_number: The called party number; this is what rules match on.
        body: The raw message body; carried as bytes and never logged by
            default (AGENT.md §13: payload logging is explicit and off).
    """

    method: str
    request_uri: str
    call_id: str
    calling_number: str
    called_number: str
    body: bytes


class SipAdapter(Protocol):
    """The boundary the stack binding implements; the kernel only needs this.

    Implementations are supplied by the M2b reSIProcate binding (ADR-0019).
    Nothing in this module opens a socket, parses a message or owns a
    transaction --- those are the binding's job, which is precisely why the
    kernel can be tested without it.
    """

    def parse(self, raw: bytes) -> SipRequestView | None:
        """Translate raw bytes into the boundary view.

        Args:
            raw: The bytes as received off the wire.

        Returns:
            The parsed view, or ``None`` when the message is malformed. The
            caller treats ``None`` as "discard": a message we cannot understand
            is not a call, and must never reach ``decide()``.
        """
        ...

    def respond(self, view: SipRequestView, status_code: int) -> bytes:
        """Build the bytes of a response to a request.

        Args:
            view: The request being answered.
            status_code: The SIP status code to answer with.

        Returns:
            The response as bytes, ready to send.
        """
        ...

    def forward(self, view: SipRequestView, target: str) -> bytes:
        """Build the bytes of an outbound leg request.

        Args:
            view: The inbound request that produced the decision.
            target: Where the call is to be routed.

        Returns:
            The outbound request as bytes, ready to send.
        """
        ...


def to_decision_request(view: SipRequestView, received_at: float) -> DecisionRequest:
    """Hand a boundary view to the kernel as a decision request.

    ``received_at`` is **injected by the caller**, never read here. ADR-0002:
    the moment anything on this path reads a clock, ``decide()`` stops being a
    function of its arguments --- time becomes a hidden input, idempotence
    cannot be stated and tests need a patched clock.

    Args:
        view: The boundary view to translate.
        received_at: When the request arrived, supplied by the caller.

    Returns:
        The :class:`DecisionRequest` for ``decide()``.
    """
    return DecisionRequest(
        call_id=view.call_id,
        calling_number=view.calling_number,
        called_number=view.called_number,
        received_at=received_at,
    )


def decision_to_status_code(action: DecisionAction) -> int:
    """Translate a kernel decision action into what the boundary answers.

    Args:
        action: The action decided by ``decide()``.

    Returns:
        ``603`` Decline for ``DECLINE`` (REQ-F-7, RFC 3261 §21.6.2), ``404``
        Not Found for ``NOT_FOUND`` (REQ-F-6, RFC 3261 §21.4.5), and
        ``STATUS_CONTINUE`` (``0``) for ``FORWARD`` and ``TRANSLATE`` --- those
        two produce no terminal response at all, because the call continues on
        an outbound leg built by :meth:`SipAdapter.forward`. ``0`` is not a SIP
        status code; it is this module's marker for "keep going".
    """
    if action is DecisionAction.DECLINE:
        return STATUS_DECLINE

    if action is DecisionAction.NOT_FOUND:
        return STATUS_NOT_FOUND

    return STATUS_CONTINUE
