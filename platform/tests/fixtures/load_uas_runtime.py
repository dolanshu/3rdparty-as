"""M6 harness UAS: product :class:`ResipRuntimeListener` in accept-all-invites test mode.

Stdout emits ``RESIP_RUNTIME_LISTENING`` lines from the native worker; the load
scripts parse ``udp_port=``.
"""

from __future__ import annotations

import signal
import sys

from as_platform.decision import RuleSet
from as_platform.sip.ingress import TransportIngressGate
from as_platform.sip.resip_runtime import ResipRuntimeListener
from as_platform.sip.transport import PeerPolicy, TlsConfig, TransportSeam

_HOST = "127.0.0.1"
_TLS = TlsConfig(
    certificate_path="",
    private_key_path="",
    require_client_certificate=False,
)


def _seam() -> TransportSeam:
    return TransportSeam(
        tls=_TLS,
        peer_policy=PeerPolicy(
            allowed_addresses=frozenset({_HOST}),
            allowed_certificate_ids=frozenset(),
        ),
        config_version=1,
    )


def main() -> None:
    gate = TransportIngressGate(_seam())
    listener = ResipRuntimeListener(
        gate,
        RuleSet(rules=()),
        accept_all_invites=True,
    )

    def _shutdown(*_args: object) -> None:
        listener.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    listener.start()
    signal.pause()


if __name__ == "__main__":
    main()
