"""Runtime entrypoint configuration and connection lifecycle coverage."""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
import uvicorn

from as_config_service import runtime

pytestmark = pytest.mark.unit

_KEY = base64.b64encode(b"k" * 32).decode("ascii")


def _environment() -> dict[str, str]:
    return {
        "AS_CONFIG_DSN": "postgresql://runtime:example@localhost/config",
        "AS_CONFIG_RUNTIME_ROLE": "as_config_runtime",
        "AS_AUDIT_RESOURCE_HMAC_KEY_B64": _KEY,
    }


def test_load_runtime_config_accepts_uri_and_libpq_keyword_dsns() -> None:
    valid_dsns = (
        "postgresql://runtime:example@localhost/config",
        "host=localhost port=5432 dbname=config user=runtime password=local-test-only",
    )

    for dsn in valid_dsns:
        environment = _environment()
        environment["AS_CONFIG_DSN"] = dsn
        assert runtime.load_runtime_config(environment).dsn == dsn


@pytest.mark.parametrize(
    "missing_name",
    (
        "AS_CONFIG_DSN",
        "AS_CONFIG_RUNTIME_ROLE",
        "AS_AUDIT_RESOURCE_HMAC_KEY_B64",
    ),
)
def test_required_configuration_fails_before_connecting(
    monkeypatch: pytest.MonkeyPatch, missing_name: str
) -> None:
    environment = _environment()
    environment.pop(missing_name)
    monkeypatch.setattr(runtime.os, "environ", environment)
    connect_calls = 0

    def connect(_: str) -> Any:
        nonlocal connect_calls
        connect_calls += 1
        raise AssertionError("invalid configuration must fail before connecting")

    with pytest.raises(ValueError, match=missing_name):
        runtime.create_runtime_app(connect=connect)
    assert connect_calls == 0


def test_malformed_environment_dsn_fails_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_password = "sentinel-password"
    environment = _environment()
    environment["AS_CONFIG_DSN"] = f"password={sentinel_password} host='unterminated"
    monkeypatch.setattr(runtime.os, "environ", environment)
    connect_calls = 0

    def connect(_: str) -> Any:
        nonlocal connect_calls
        connect_calls += 1
        raise AssertionError("invalid configuration must fail before connecting")

    with pytest.raises(ValueError, match="AS_CONFIG_DSN") as error:
        runtime.create_runtime_app(connect=connect)
    assert sentinel_password not in str(error.value)
    assert connect_calls == 0


@pytest.mark.parametrize(
    ("encoded_key", "message"),
    (
        ("not-base64!", "valid base64"),
        (base64.b64encode(b"short").decode("ascii"), "exactly 32 bytes"),
    ),
)
def test_audit_hmac_key_must_be_valid_base64_for_exactly_32_bytes(
    encoded_key: str, message: str
) -> None:
    environment = _environment()
    environment["AS_AUDIT_RESOURCE_HMAC_KEY_B64"] = encoded_key

    with pytest.raises(ValueError, match=message) as error:
        runtime.load_runtime_config(environment)
    assert encoded_key not in str(error.value)


def test_proxy_headers_require_explicit_non_wildcard_trust() -> None:
    environment = _environment()
    environment["AS_CONFIG_PROXY_HEADERS"] = "true"

    with pytest.raises(ValueError, match="AS_CONFIG_TRUSTED_PROXIES"):
        runtime.load_runtime_config(environment)

    environment["AS_CONFIG_TRUSTED_PROXIES"] = "*"
    with pytest.raises(ValueError, match="wildcard"):
        runtime.load_runtime_config(environment)


def test_config_schema_defaults_to_dedicated_schema() -> None:
    assert runtime.load_runtime_config(_environment()).config_schema == "as_config"


@pytest.mark.parametrize(
    ("config_schema", "audit_schema", "message"),
    (
        ("public", "console_audit", "AS_CONFIG_SCHEMA"),
        ("console_audit", "console_audit", "must differ"),
    ),
)
def test_runtime_rejects_public_or_shared_schemas_before_connecting(
    config_schema: str,
    audit_schema: str,
    message: str,
) -> None:
    environment = _environment()
    environment["AS_CONFIG_SCHEMA"] = config_schema
    environment["AS_AUDIT_SCHEMA"] = audit_schema
    connect_calls = 0

    def connect(_: str) -> Any:
        nonlocal connect_calls
        connect_calls += 1
        raise AssertionError("invalid schema configuration must fail before connecting")

    with pytest.raises(ValueError, match=message):
        runtime.create_runtime_app(runtime.load_runtime_config(environment), connect=connect)
    assert connect_calls == 0


@pytest.mark.parametrize("network", ("0.0.0.0/0", "::/0"))
def test_proxy_headers_reject_default_routes(network: str) -> None:
    environment = _environment()
    environment["AS_CONFIG_PROXY_HEADERS"] = "true"
    environment["AS_CONFIG_TRUSTED_PROXIES"] = network

    with pytest.raises(ValueError, match="default route"):
        runtime.load_runtime_config(environment)


def test_main_uses_loopback_defaults_without_proxy_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime.os, "environ", _environment())
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert runtime.main() == 0
    assert calls == [
        (
            ("as_config_service.runtime:create_runtime_app",),
            {
                "factory": True,
                "host": "127.0.0.1",
                "port": 8000,
                "proxy_headers": False,
                "forwarded_allow_ips": "",
            },
        )
    ]


def test_main_passes_normalized_trusted_proxies_to_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _environment()
    environment.update(
        {
            "AS_CONFIG_HOST": "0.0.0.0",
            "AS_CONFIG_PORT": "8123",
            "AS_CONFIG_PROXY_HEADERS": "true",
            "AS_CONFIG_TRUSTED_PROXIES": "192.0.2.7, 2001:db8::1/64",
        }
    )
    monkeypatch.setattr(runtime.os, "environ", environment)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert runtime.main() == 0
    assert calls == [
        (
            ("as_config_service.runtime:create_runtime_app",),
            {
                "factory": True,
                "host": "0.0.0.0",
                "port": 8123,
                "proxy_headers": True,
                "forwarded_allow_ips": "192.0.2.7/32,2001:db8::/64",
            },
        )
    ]


@pytest.mark.parametrize("trusted_proxy", ("*", "0.0.0.0/0", "::/0"))
def test_main_rejects_unsafe_proxy_trust_without_leaking_secrets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    trusted_proxy: str,
) -> None:
    dsn = "postgresql://private-user:private-password@db/private-config"
    encoded_key = base64.b64encode(b"s" * 32).decode("ascii")
    environment = _environment()
    environment.update(
        {
            "AS_CONFIG_DSN": dsn,
            "AS_AUDIT_RESOURCE_HMAC_KEY_B64": encoded_key,
            "AS_CONFIG_PROXY_HEADERS": "true",
            "AS_CONFIG_TRUSTED_PROXIES": trusted_proxy,
        }
    )
    monkeypatch.setattr(runtime.os, "environ", environment)
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert runtime.main() != 0
    assert calls == []
    error = capsys.readouterr().err
    assert dsn not in error
    assert encoded_key not in error


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("audit_resource_hmac_key", b"short"),
        ("runtime_role", "invalid;role"),
        ("config_schema", "public"),
    ),
)
def test_supplied_runtime_config_is_validated_before_connecting(field: str, value: Any) -> None:
    config = replace(runtime.load_runtime_config(_environment()), **{field: value})
    connect_calls = 0

    def connect(_: str) -> Any:
        nonlocal connect_calls
        connect_calls += 1
        raise AssertionError("invalid configuration must fail before connecting")

    with pytest.raises(ValueError):
        runtime.create_runtime_app(config, connect=connect)
    assert connect_calls == 0


def test_malformed_supplied_dsn_fails_before_connecting() -> None:
    sentinel_password = "sentinel-password"
    config = replace(
        runtime.load_runtime_config(_environment()),
        dsn=f"password={sentinel_password} host='unterminated",
    )
    connect_calls = 0

    def connect(_: str) -> Any:
        nonlocal connect_calls
        connect_calls += 1
        raise AssertionError("invalid configuration must fail before connecting")

    with pytest.raises(ValueError, match="AS_CONFIG_DSN") as error:
        runtime.create_runtime_app(config, connect=connect)
    assert sentinel_password not in str(error.value)
    assert connect_calls == 0


class _Cursor:
    def __init__(self, events: list[tuple[Any, ...]]) -> None:
        self.events = events

    def execute(self, query: Any, params: tuple[object, ...] = ()) -> None:
        self.events.append(("role", query.as_string()))

    def fetchone(self) -> tuple[Any, ...] | None:
        return None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return []

    def close(self) -> None:
        self.events.append(("cursor-close",))


class _Connection:
    info: Any = None

    def __init__(self, events: list[tuple[Any, ...]]) -> None:
        self.events = events
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor(self.events)

    def commit(self) -> None:
        self.events.append(("commit",))

    def rollback(self) -> None:
        self.events.append(("rollback",))

    def close(self) -> None:
        self.closed = True
        self.events.append(("connection-close",))


class _Router:
    def __init__(self) -> None:
        self.shutdown_handlers: list[Callable[[], None]] = []

    def add_event_handler(self, event: str, handler: Callable[[], None]) -> None:
        assert event == "shutdown"
        self.shutdown_handlers.append(handler)


class _App:
    def __init__(self) -> None:
        self.router = _Router()


def _replace_stores(monkeypatch: pytest.MonkeyPatch, events: list[tuple[Any, ...]]) -> None:
    for name in (
        "PostgresManagedRuleStore",
        "PostgresChangeOrderStore",
        "PostgresDistributionStore",
        "PostgresConsoleAuthStore",
        "PostgresAsInstanceStore",
        "PostgresAuditStore",
    ):

        def constructor(connection: Any, *, _name: str = name, **kwargs: Any) -> Any:
            events.append(("store", _name, connection, kwargs))

            class Store:
                def ensure_schema(self) -> None:
                    raise AssertionError("runtime startup must not create schemas")

            return Store()

        monkeypatch.setattr(runtime, name, constructor)


def test_runtime_uses_one_connection_and_sets_role_before_app_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[Any, ...]] = []
    connection = _Connection(events)
    app = _App()
    config = runtime.load_runtime_config(_environment())
    _replace_stores(monkeypatch, events)

    def create_app(**kwargs: Any) -> _App:
        events.append(("app", kwargs))
        assert kwargs["resolve_identity"] is None
        assert kwargs["audit_resource_hmac_key"] == b"k" * 32
        assert all(
            kwargs[name].ensure_schema.__self__ is not None
            for name in (
                "managed_rule_store",
                "change_order_store",
                "distribution_store",
                "auth_store",
                "as_instance_store",
                "audit_store",
            )
        )
        for name in (
            "can_read_config",
            "can_submit_change",
            "can_approve_change",
            "can_manage_users",
        ):
            assert kwargs[name](object()) is False
        return app

    monkeypatch.setattr(runtime, "create_app", create_app)

    result = runtime.create_runtime_app(config, connect=lambda dsn: connection)

    assert result is app
    assert events[0] == ("role", 'SET ROLE "as_config_runtime"')
    assert events[1] == ("cursor-close",)
    assert events[2] == ("commit",)
    assert events[3] == ("role", 'SET search_path TO "as_config", pg_catalog')
    assert events[4] == ("cursor-close",)
    assert events[5] == ("commit",)
    store_events = [event for event in events if event[0] == "store"]
    assert len(store_events) == 6
    assert all(event[2] is connection for event in store_events)
    assert events[-1][0] == "app"
    assert app.router.shutdown_handlers == [connection.close]
    assert not connection.closed


def test_app_construction_failure_closes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[Any, ...]] = []
    connection = _Connection(events)
    _replace_stores(monkeypatch, events)

    def create_app(**_: Any) -> Any:
        raise RuntimeError("construction failed")

    monkeypatch.setattr(runtime, "create_app", create_app)

    with pytest.raises(RuntimeError, match="construction failed"):
        runtime.create_runtime_app(
            runtime.load_runtime_config(_environment()), connect=lambda dsn: connection
        )
    assert connection.closed
    assert events[-1] == ("connection-close",)
