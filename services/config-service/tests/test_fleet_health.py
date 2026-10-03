"""Unit coverage for fleet health JSON parsing and probes."""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request

import pytest

from as_config_service.fleet_health import (
    FleetHealthProbeError,
    parse_health_json,
    probe_instance_health,
)

pytestmark = pytest.mark.unit


class _OkResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return 200

    def __enter__(self) -> _OkResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_parse_health_json_accepts_strict_boolean_object() -> None:
    assert parse_health_json(b'{"healthy": true}') is True
    assert parse_health_json(b'{"healthy": false}') is False


@pytest.mark.parametrize(
    "body",
    (
        b"not-json",
        b"[]",
        b'{"healthy": "yes"}',
        b'{"healthy": true, "extra": false}',
        b"{}",
    ),
)
def test_parse_health_json_rejects_nonconforming_payloads(body: bytes) -> None:
    with pytest.raises(FleetHealthProbeError):
        parse_health_json(body)


def test_probe_instance_health_uses_injected_opener() -> None:
    seen: list[Request] = []

    def opener(request: Request, *, timeout: float) -> Any:
        seen.append(request)
        assert timeout == 5.0
        return _OkResponse(json.dumps({"healthy": True}).encode("utf-8"))

    assert probe_instance_health("http://127.0.0.1/health", opener=opener) is True
    assert seen[0].full_url == "http://127.0.0.1/health"
    assert seen[0].method == "GET"
