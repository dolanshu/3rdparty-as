"""Runtime ingress gate: apply transport seam peer policy at connection accept.

This is the Python binding seam reSIProcate must call before handing SIP into the
kernel (ADR-0016). Policy evaluation stays on :class:`~as_platform.sip.transport.TransportSeam`;
this module holds the **current** seam for new connections and delegates
``allows`` at ingress. Hot rotation swaps the seam via :meth:`TransportIngressGate.install`
or :meth:`TransportIngressGate.install_with_overlap` for REQ-S-3 dual-material windows;
holders of an older seam snapshot are unaffected, matching
:class:`~as_platform.sip.transport.TransportSeam.reload` immutability.

See ADR-0016: fail-closed peer whitelist at the single S-SBC-facing entry;
plaintext SIP when TLS is required must be rejected before payload processing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from as_platform.sip.tls_rotation import TlsRotationState
from as_platform.sip.transport import PeerIdentity, TransportSeam

_PLAINTEXT_OK_TRANSPORTS = frozenset({"tls", "sips"})


class TransportIngressGate:
    """Thread-safe holder for the transport seam used on new ingress checks."""

    def __init__(
        self,
        seam: TransportSeam,
        *,
        on_overlap_started: Callable[[], None] | None = None,
    ) -> None:
        """Create a gate seeded with the initial seam.

        Args:
            seam: Policy and TLS configuration for peers accepted from this point on.
            on_overlap_started: Optional hook when :meth:`install_with_overlap` begins
                (for example native ``reloadCertificates``).
        """
        self._lock = threading.Lock()
        self._seam = seam
        self._retiring_seam: TransportSeam | None = None
        self._overlap_deadline_monotonic: float | None = None
        self._legacy_connection_ids: set[str] = set()
        self._registered_connection_ids: set[str] = set()
        self._tls_rotation = TlsRotationState(active=seam.tls)
        self._on_overlap_started = on_overlap_started

    def install(self, seam: TransportSeam) -> TransportSeam:
        """Replace the active seam; new checks use ``seam`` immediately.

        Clears any in-progress overlap window.

        Args:
            seam: The next transport configuration version.

        Returns:
            The seam that was in force before this call.
        """
        with self._lock:
            previous = self._seam
            self._seam = seam
            self._clear_overlap_state()
            self._tls_rotation = TlsRotationState(active=seam.tls)
            return previous

    def install_with_overlap(self, seam: TransportSeam, overlap_seconds: float) -> TransportSeam:
        """Promote ``seam`` for new connections while retaining the prior seam for legacy tokens.

        Connections already :meth:`register_connection` before this call keep the
        retiring seam for :meth:`check_peer` until the monotonic overlap deadline.
        New registrations after this call use only the active seam.

        Args:
            seam: Next transport configuration (typically new TLS material).
            overlap_seconds: Duration to honor retiring policy for legacy connection tokens.

        Returns:
            The seam that was active before overlap began (now retiring).
        """
        hook: Callable[[], None] | None = None
        with self._lock:
            now = time.monotonic()
            previous = self._seam
            self._retiring_seam = previous
            self._seam = seam
            self._overlap_deadline_monotonic = now + overlap_seconds
            self._legacy_connection_ids = set(self._registered_connection_ids)
            self._tls_rotation = self._tls_rotation.start_overlap(
                seam.tls, overlap_seconds, now=now
            )
            hook = self._on_overlap_started

        if hook is not None:
            hook()

        return previous

    @property
    def tls_rotation(self) -> TlsRotationState:
        """Snapshot of server TLS overlap state (for tests and bindings)."""
        with self._lock:
            now = time.monotonic()
            self._expire_overlap_if_needed(now)
            return self._tls_rotation

    def attach_overlap_hook(self, hook: Callable[[], None] | None) -> None:
        """Set ``on_overlap_started`` when the gate was constructed without one."""
        if hook is None:
            return
        with self._lock:
            if self._on_overlap_started is None:
                self._on_overlap_started = hook

    def current_seam(self) -> TransportSeam:
        """Return the active transport seam (immutable snapshot)."""
        with self._lock:
            return self._seam

    _MAX_REGISTERED_CONNECTIONS = 4096

    def register_connection(self, connection_id: str) -> None:
        """Record a connection token accepted by the stack binding."""
        with self._lock:
            self._registered_connection_ids.add(connection_id)
            if len(self._registered_connection_ids) > self._MAX_REGISTERED_CONNECTIONS:
                overflow = sorted(self._registered_connection_ids - self._legacy_connection_ids)
                for token in overflow[: len(overflow) // 2]:
                    self._registered_connection_ids.discard(token)

    def unregister_connection(self, connection_id: str) -> None:
        """Drop a connection token when the transport closes."""
        with self._lock:
            self._registered_connection_ids.discard(connection_id)
            self._legacy_connection_ids.discard(connection_id)

    def check_peer(self, peer: PeerIdentity, connection_id: str | None = None) -> bool:
        """Whether ``peer`` is authorised under the applicable seam.

        Args:
            peer: Observed source identity (from stack binding or test listener).
            connection_id: Stable connection token from the binding. When provided and
                the token was registered before the current overlap window began,
                retiring policy applies until the overlap deadline.

        Returns:
            ``True`` when the peer is allowed to send traffic, ``False`` to drop.
        """
        with self._lock:
            now = time.monotonic()
            self._expire_overlap_if_needed(now)
            seam = self._seam
            if (
                connection_id is not None
                and self._retiring_seam is not None
                and connection_id in self._legacy_connection_ids
                and self._overlap_deadline_monotonic is not None
                and now < self._overlap_deadline_monotonic
            ):
                seam = self._retiring_seam
            return seam.allows(peer)

    def _clear_overlap_state(self) -> None:
        self._retiring_seam = None
        self._overlap_deadline_monotonic = None
        self._legacy_connection_ids.clear()

    def _expire_overlap_if_needed(self, now: float) -> None:
        if self._overlap_deadline_monotonic is None or now < self._overlap_deadline_monotonic:
            return
        self._clear_overlap_state()
        self._tls_rotation = self._tls_rotation.expire(now)


def reject_plaintext_when_tls_required(tls_required: bool, transport: str) -> bool:
    """Whether ingress must reject a connection on ``transport`` (ADR-0016).

    When TLS is mandated for the trunk, only ``tls`` and ``sips`` transports are
    acceptable; plain UDP/TCP SIP must be denied before message parsing.

    Args:
        tls_required: Whether end-to-end TLS is required for this listener/trunk.
        transport: Stack transport label (for example ``udp``, ``tcp``, ``tls``, ``sips``).

    Returns:
        ``True`` when the connection must be rejected, ``False`` when it may proceed
        to peer-policy checks.
    """
    if not tls_required:
        return False
    return transport.casefold() not in _PLAINTEXT_OK_TRANSPORTS
