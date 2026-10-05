"""REQ-S-3 dual-certificate overlap state (pure logic).

Maps to ``docs/acceptance/test-plan.md`` §3 REQ-S-3 (policy layer only):

- **In-flight calls during overlap:** retiring :class:`~as_platform.sip.transport.TlsConfig`
  (via the gate's retiring seam) applies to **registered** connection tokens until the
  monotonic overlap deadline.
- **New TLS connections:** :meth:`TlsRotationState.tls_for_new_connections` and the active
  seam apply to tokens registered after
  :meth:`~as_platform.sip.ingress.TransportIngressGate.install_with_overlap`.
- **Retire old material:** :meth:`TlsRotationState.expire` clears retiring TLS after the
  deadline.
- **No process restart:** value-level rotation; stack ``reloadCertificates`` is requested on
  overlap start.

Live TLS handshake proof, operator PKI, and active-dialog continuity on the product transport
are still required for full REQ-S-3 acceptance.
"""

from __future__ import annotations

from dataclasses import dataclass

from as_platform.sip.transport import TlsConfig


@dataclass(frozen=True)
class TlsRotationState:
    """Active and optionally retiring server TLS material during an overlap window."""

    active: TlsConfig
    retiring: TlsConfig | None = None
    overlap_deadline_monotonic: float | None = None

    def start_overlap(
        self,
        next_active: TlsConfig,
        overlap_seconds: float,
        *,
        now: float,
    ) -> TlsRotationState:
        """Begin overlap: promote ``next_active`` and retain previous ``active`` as retiring."""
        if overlap_seconds < 0:
            raise ValueError("overlap_seconds must be non-negative")
        return TlsRotationState(
            active=next_active,
            retiring=self.active,
            overlap_deadline_monotonic=now + overlap_seconds,
        )

    def overlap_in_effect(self, now: float) -> bool:
        """Whether the retiring certificate window is still open."""
        if self.retiring is None or self.overlap_deadline_monotonic is None:
            return False
        return now < self.overlap_deadline_monotonic

    def expire(self, now: float) -> TlsRotationState:
        """Drop retiring material once the overlap deadline has passed."""
        if self.overlap_in_effect(now):
            return self
        return TlsRotationState(active=self.active, retiring=None, overlap_deadline_monotonic=None)

    def tls_for_new_connections(self) -> TlsConfig:
        """TLS files presented on new listener handshakes after overlap starts."""
        return self.active

    def tls_for_existing_connections(self, now: float) -> TlsConfig | None:
        """TLS context still honored for pre-rotation connections during overlap."""
        if self.overlap_in_effect(now):
            return self.retiring
        return None
