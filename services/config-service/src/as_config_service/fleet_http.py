"""Small urllib helpers for fleet outbound HTTP."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener, urlopen

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def urlopen_for_request(request: Request, *, timeout: float) -> Any:
    """Open ``request``, bypassing HTTP(S)_PROXY for loopback targets."""
    host = (urlparse(request.full_url).hostname or "").lower()
    if host in _LOOPBACK_HOSTS:
        return build_opener(ProxyHandler({})).open(request, timeout=timeout)
    return urlopen(request, timeout=timeout)
