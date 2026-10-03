"""Outbound distribution-start notifications to fleet AS instances. REQ-F-15 / M4b-7.5.

Full production AS stack re-test after fleet wiring remains 补测 (out of this engineering slice).
"""

from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request

from as_config_service.fleet_http import urlopen_for_request

_DEFAULT_TIMEOUT_SECONDS = 5.0


class FleetNotifyError(Exception):
    """Raised when a notify URL cannot be reached or returns a non-success status."""


class _HttpPoster(Protocol):
    def __call__(self, request: Request, *, timeout: float) -> Any: ...


def build_notify_payload(change_id: str, version: int, bundle_version: str) -> bytes:
    """Serialize the distribution-start notify body."""
    if not isinstance(change_id, str) or not change_id.strip():
        raise ValueError("change_id must be a nonblank string")
    if type(version) is not int or version < 1:
        raise ValueError("version must be a positive integer")
    if not isinstance(bundle_version, str) or not bundle_version.strip():
        raise ValueError("bundle_version must be a nonblank string")
    encoded = json.dumps(
        {
            "change_id": change_id,
            "version": version,
            "bundle_version": bundle_version.strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return encoded.encode("utf-8")


def post_distribution_notify(
    notify_url: str,
    payload: bytes,
    *,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    opener: _HttpPoster | None = None,
) -> None:
    """POST JSON ``payload`` to ``notify_url``; raise on transport or HTTP failure."""
    if not isinstance(notify_url, str) or not notify_url.strip():
        raise ValueError("notify_url must be a nonblank string")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    request = Request(
        notify_url.strip(),
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    poster = urlopen_for_request if opener is None else opener
    try:
        with poster(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
    except HTTPError as exc:
        raise FleetNotifyError(f"notify HTTP {exc.code}") from exc
    except URLError as exc:
        raise FleetNotifyError("notify request failed") from exc
    if int(status) < 200 or int(status) >= 300:
        raise FleetNotifyError(f"notify HTTP {status}")
