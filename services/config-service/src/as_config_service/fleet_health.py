"""Testbed-friendly HTTP health probes for fleet instances. REQ-F-15 / M4b-7.5."""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request

from as_config_service.fleet_http import urlopen_for_request

_DEFAULT_TIMEOUT_SECONDS = 5.0


class FleetHealthProbeError(Exception):
    """Raised when a health URL cannot be reached or returns an invalid body."""


class _HttpReader(Protocol):
    def __call__(self, request: Request, *, timeout: float) -> Any: ...


def parse_health_json(body: bytes) -> bool:
    """Decode a strict ``{"healthy": <bool>}`` health response."""
    if not isinstance(body, bytes):
        raise TypeError("body must be bytes")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FleetHealthProbeError("health response is not valid JSON") from exc
    if type(payload) is not dict or set(payload) != {"healthy"}:
        raise FleetHealthProbeError('health response must be exactly {"healthy": <bool>}')
    healthy = payload["healthy"]
    if type(healthy) is not bool:
        raise FleetHealthProbeError("health.healthy must be a bool")
    return healthy


def probe_instance_health(
    health_url: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    opener: _HttpReader | None = None,
) -> bool:
    """GET ``health_url`` and return the parsed ``healthy`` flag."""
    if not isinstance(health_url, str) or not health_url.strip():
        raise ValueError("health_url must be a nonblank string")
    request = Request(health_url.strip(), method="GET")
    reader = urlopen_for_request if opener is None else opener
    try:
        with reader(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = response.read()
    except HTTPError as exc:
        raise FleetHealthProbeError(f"health probe HTTP {exc.code}") from exc
    except URLError as exc:
        raise FleetHealthProbeError("health probe request failed") from exc
    if int(status) < 200 or int(status) >= 300:
        raise FleetHealthProbeError(f"health probe HTTP {status}")
    try:
        return parse_health_json(body)
    except FleetHealthProbeError:
        raise
    except (TypeError, ValueError) as exc:
        raise FleetHealthProbeError("health response is invalid") from exc
