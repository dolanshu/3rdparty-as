"""Unit coverage for fleet notify payload encoding."""

from __future__ import annotations

import json
from typing import Any
from urllib.request import Request

import pytest

from as_config_service.fleet_notify import build_notify_payload, post_distribution_notify

pytestmark = pytest.mark.unit


class _OkResponse:
    def getcode(self) -> int:
        return 200

    def __enter__(self) -> _OkResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_build_notify_payload_is_deterministic_json() -> None:
    payload = build_notify_payload("change-1", 7, "7")

    assert payload == b'{"bundle_version":"7","change_id":"change-1","version":7}'
    assert json.loads(payload.decode("utf-8")) == {
        "change_id": "change-1",
        "version": 7,
        "bundle_version": "7",
    }


def test_post_distribution_notify_uses_injected_opener() -> None:
    captured: list[tuple[Request, bytes]] = []

    def opener(request: Request, *, timeout: float) -> Any:
        captured.append((request, request.data))
        return _OkResponse()

    body = build_notify_payload("co-1", 3, "3")
    post_distribution_notify("http://127.0.0.1/notify", body, opener=opener)

    request, data = captured[0]
    assert request.full_url == "http://127.0.0.1/notify"
    assert request.method == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert data == body
