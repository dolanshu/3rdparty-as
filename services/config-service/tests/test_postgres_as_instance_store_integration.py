"""PostgreSQL coverage for fleet instance inventory."""

from __future__ import annotations

import json
import os
import threading
import uuid
import warnings
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlparse

import pytest

from as_config_service.as_instance import AsInstance, AsUseCase
from as_config_service.as_instance_store import (
    DuplicateAsInstanceError,
    PostgresAsInstanceStore,
    StaleAsInstanceRevisionError,
)
from as_config_service.fleet_health import probe_instance_health
from as_config_service.fleet_notify import build_notify_payload, post_distribution_notify

pytestmark = pytest.mark.integration

TEST_DSN = os.environ.get(
    "AS_PG_TEST_DSN", "postgresql://postgres:secret@127.0.0.1:55432/as_config"
)
_CONNECT_TIMEOUT_SECONDS = 3
_NOW = 1_700_000_000.0
_NETWORK_UNAVAILABLE_MESSAGES = (
    "connection refused",
    "connection timed out",
    "timeout expired",
    "operation timed out",
    "no route to host",
    "network is unreachable",
)


@dataclass(frozen=True)
class PgHarness:
    store: PostgresAsInstanceStore
    connection: Any
    prefix: str


def _is_network_unavailable(exc: BaseException, operational_error: type[BaseException]) -> bool:
    if not isinstance(exc, operational_error):
        return False
    normalized = str(exc).lower()
    return any(marker in normalized for marker in _NETWORK_UNAVAILABLE_MESSAGES)


@pytest.fixture()
def pg() -> Iterator[PgHarness]:
    psycopg = pytest.importorskip("psycopg")
    parsed = urlparse(TEST_DSN)
    connection = None
    prefix = f"as_instance_test_{uuid.uuid4().hex[:10]}"
    try:
        try:
            connection = psycopg.connect(TEST_DSN, connect_timeout=_CONNECT_TIMEOUT_SECONDS)
        except Exception as exc:
            if _is_network_unavailable(exc, psycopg.OperationalError):
                pytest.skip(
                    f"no PostgreSQL server reachable at {parsed.hostname}:{parsed.port}: {exc}"
                )
            raise
        store = PostgresAsInstanceStore(connection, prefix=prefix, schema="public")
        store.ensure_schema()
        yield PgHarness(store=store, connection=connection, prefix=prefix)
    finally:
        if connection is not None:
            with suppress(Exception):
                cursor = connection.cursor()
                cursor.execute(f'DROP TABLE IF EXISTS public."{prefix}"')
                connection.commit()
                cursor.close()
            with suppress(Exception):
                connection.close()


def test_inventory_round_trip_and_revision_cas(pg: PgHarness) -> None:
    instance = AsInstance(
        instance_id="as-1",
        use_case=AsUseCase.ANTI_FRAUD,
        notify_url="http://127.0.0.1/notify",
        health_url=None,
        enabled=True,
    )
    created = pg.store.create(instance, "change-1", "ops", _NOW)
    assert created.revision == 1
    assert pg.store.list_all() == (created,)

    with pytest.raises(DuplicateAsInstanceError):
        pg.store.create(instance, "change-dup", "ops", _NOW + 0.5)

    updated_instance = AsInstance(
        instance_id="as-1",
        use_case=AsUseCase.TRANSLATION,
        notify_url=None,
        health_url="http://127.0.0.1/health",
        enabled=False,
    )
    updated = pg.store.update(updated_instance, "change-2", "ops", _NOW + 1, 1)
    assert updated.revision == 2
    assert pg.store.get("as-1") == updated

    with pytest.raises(StaleAsInstanceRevisionError):
        pg.store.update(updated_instance, "change-3", "ops", _NOW + 2, 1)

    pg.store.delete("as-1", "change-4", "ops", _NOW + 3, 2)
    assert pg.store.get("as-1") is None

    recreated = pg.store.create(instance, "change-5", "ops", _NOW + 4)
    assert recreated.revision == 1
    assert pg.store.get("as-1") == recreated


def test_notify_and_health_against_threaded_mock_server(pg: PgHarness) -> None:
    received: list[bytes] = []
    health_flag = {"healthy": True}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            received.append(self.rfile.read(length))
            self.send_response(204)
            self.end_headers()

        def do_GET(self) -> None:
            body = json.dumps(health_flag).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base = f"http://{host}:{port}"
    try:
        payload = build_notify_payload("change-9", 9, "9")
        post_distribution_notify(f"{base}/notify", payload)
        assert json.loads(received[0].decode("utf-8"))["bundle_version"] == "9"
        assert probe_instance_health(f"{base}/health") is True
        health_flag["healthy"] = False
        assert probe_instance_health(f"{base}/health") is False
    finally:
        server.shutdown()
        thread.join(timeout=2)
        warnings.filterwarnings("ignore", category=pytest.PytestWarning)
