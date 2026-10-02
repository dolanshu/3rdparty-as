"""Production ASGI runtime wiring for the config service."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import os
import re
import sys
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from as_config_service.api import ApiIdentity, create_app
from as_config_service.audit_store import PostgresAuditStore
from as_config_service.auth import PostgresConsoleAuthStore
from as_config_service.change_order_store import PostgresChangeOrderStore
from as_config_service.distribution_store import PostgresDistributionStore
from as_config_service.managed_rule_store import PostgresManagedRuleStore

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")


class _RuntimeCursor(Protocol):
    def execute(self, query: Any, params: tuple[object, ...] = ()) -> Any: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def close(self) -> None: ...


class _RuntimeConnection(Protocol):
    info: Any

    def cursor(self) -> _RuntimeCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class RuntimeConfig:
    """Validated runtime settings, with credential values hidden from repr."""

    dsn: str = field(repr=False)
    runtime_role: str
    audit_resource_hmac_key: bytes = field(repr=False)
    config_schema: str = "as_config"
    audit_schema: str = "console_audit"
    host: str = "127.0.0.1"
    port: int = 8000
    proxy_headers: bool = False
    trusted_proxies: tuple[str, ...] = ()


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if value is None or not value.strip():
        raise ValueError(f"{name} must be set")
    return value.strip()


def _validate_dsn(dsn: str) -> None:
    try:
        conninfo_to_dict(dsn)
    except (psycopg.Error, ValueError):
        raise ValueError("AS_CONFIG_DSN must be a valid PostgreSQL connection string") from None


def _identifier(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, default).strip()
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a valid PostgreSQL identifier")
    return value


def _trusted_proxies(value: str | None, *, required: bool) -> tuple[str, ...]:
    if value is None:
        if required:
            raise ValueError("AS_CONFIG_TRUSTED_PROXIES must be set when proxy headers are enabled")
        return ()
    entries = value.split(",")
    if not entries or any(not entry.strip() for entry in entries):
        raise ValueError("AS_CONFIG_TRUSTED_PROXIES must contain explicit IP addresses or CIDRs")
    networks: list[str] = []
    for entry in entries:
        candidate = entry.strip()
        networks.append(_validated_trusted_proxy(candidate))
    return tuple(networks)


def _validated_trusted_proxy(candidate: str) -> str:
    if candidate == "*":
        raise ValueError("AS_CONFIG_TRUSTED_PROXIES must not contain a wildcard")
    try:
        network = ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        raise ValueError(
            "AS_CONFIG_TRUSTED_PROXIES must contain valid IP addresses or CIDRs"
        ) from None
    if network.prefixlen == 0:
        raise ValueError("AS_CONFIG_TRUSTED_PROXIES must not contain a default route")
    return str(network)


def load_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    """Load and strictly validate runtime settings before opening a connection."""
    source = os.environ if env is None else env
    dsn = _required(source, "AS_CONFIG_DSN")
    _validate_dsn(dsn)
    runtime_role = _required(source, "AS_CONFIG_RUNTIME_ROLE")
    if not _IDENTIFIER.fullmatch(runtime_role):
        raise ValueError("AS_CONFIG_RUNTIME_ROLE must be a valid PostgreSQL identifier")

    encoded_key = _required(source, "AS_AUDIT_RESOURCE_HMAC_KEY_B64")
    try:
        audit_key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("AS_AUDIT_RESOURCE_HMAC_KEY_B64 must be valid base64") from None
    if len(audit_key) != 32:
        raise ValueError("AS_AUDIT_RESOURCE_HMAC_KEY_B64 must decode to exactly 32 bytes")

    config_schema = _identifier(source, "AS_CONFIG_SCHEMA", "as_config")
    audit_schema = _identifier(source, "AS_AUDIT_SCHEMA", "console_audit")
    if config_schema == "public":
        raise ValueError("AS_CONFIG_SCHEMA must not be public")
    if audit_schema == "public":
        raise ValueError("AS_AUDIT_SCHEMA must not be public")
    if config_schema == audit_schema:
        raise ValueError("AS_CONFIG_SCHEMA and AS_AUDIT_SCHEMA must differ")

    host = source.get("AS_CONFIG_HOST", "127.0.0.1").strip()
    if not host:
        raise ValueError("AS_CONFIG_HOST must not be empty")
    raw_port = source.get("AS_CONFIG_PORT", "8000")
    if not re.fullmatch(r"[0-9]+", raw_port):
        raise ValueError("AS_CONFIG_PORT must be an integer from 1 to 65535")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise ValueError("AS_CONFIG_PORT must be an integer from 1 to 65535")

    raw_proxy_headers = source.get("AS_CONFIG_PROXY_HEADERS", "false")
    if raw_proxy_headers not in {"true", "false"}:
        raise ValueError("AS_CONFIG_PROXY_HEADERS must be 'true' or 'false'")
    proxy_headers = raw_proxy_headers == "true"
    trusted_proxies = _trusted_proxies(
        source.get("AS_CONFIG_TRUSTED_PROXIES"), required=proxy_headers
    )

    return RuntimeConfig(
        dsn=dsn,
        runtime_role=runtime_role,
        audit_resource_hmac_key=audit_key,
        config_schema=config_schema,
        audit_schema=audit_schema,
        host=host,
        port=port,
        proxy_headers=proxy_headers,
        trusted_proxies=trusted_proxies,
    )


def _deny(_: ApiIdentity) -> bool:
    return False


def _validate_runtime_config(settings: RuntimeConfig) -> None:
    if not isinstance(settings.dsn, str) or not settings.dsn.strip():
        raise ValueError("AS_CONFIG_DSN must be set")
    _validate_dsn(settings.dsn)
    if not isinstance(settings.runtime_role, str) or not _IDENTIFIER.fullmatch(
        settings.runtime_role
    ):
        raise ValueError("AS_CONFIG_RUNTIME_ROLE must be a valid PostgreSQL identifier")
    if (
        not isinstance(settings.audit_resource_hmac_key, bytes)
        or len(settings.audit_resource_hmac_key) != 32
    ):
        raise ValueError("AS_AUDIT_RESOURCE_HMAC_KEY_B64 must decode to exactly 32 bytes")
    if not isinstance(settings.config_schema, str) or not _IDENTIFIER.fullmatch(
        settings.config_schema
    ):
        raise ValueError("AS_CONFIG_SCHEMA must be a valid PostgreSQL identifier")
    if not isinstance(settings.audit_schema, str) or not _IDENTIFIER.fullmatch(
        settings.audit_schema
    ):
        raise ValueError("AS_AUDIT_SCHEMA must be a valid PostgreSQL identifier")
    if settings.audit_schema == "public":
        raise ValueError("AS_AUDIT_SCHEMA must not be public")
    if settings.config_schema == "public":
        raise ValueError("AS_CONFIG_SCHEMA must not be public")
    if settings.config_schema == settings.audit_schema:
        raise ValueError("AS_CONFIG_SCHEMA and AS_AUDIT_SCHEMA must differ")
    if not isinstance(settings.host, str) or not settings.host.strip():
        raise ValueError("AS_CONFIG_HOST must not be empty")
    if type(settings.port) is not int or not 1 <= settings.port <= 65535:
        raise ValueError("AS_CONFIG_PORT must be an integer from 1 to 65535")
    if type(settings.proxy_headers) is not bool:
        raise ValueError("AS_CONFIG_PROXY_HEADERS must be a boolean")
    if not isinstance(settings.trusted_proxies, tuple):
        raise ValueError("AS_CONFIG_TRUSTED_PROXIES must contain explicit IP addresses or CIDRs")
    for proxy in settings.trusted_proxies:
        if not isinstance(proxy, str) or not proxy:
            raise ValueError(
                "AS_CONFIG_TRUSTED_PROXIES must contain explicit IP addresses or CIDRs"
            )
        _validated_trusted_proxy(proxy)
    if settings.proxy_headers and not settings.trusted_proxies:
        raise ValueError("AS_CONFIG_TRUSTED_PROXIES must be set when proxy headers are enabled")


def _close_quietly(connection: _RuntimeConnection) -> None:
    with suppress(Exception):
        connection.close()


def create_runtime_app(
    config: RuntimeConfig | None = None,
    *,
    connect: Callable[[str], _RuntimeConnection] | None = None,
) -> Any:
    """Assemble the API using one dedicated, pre-provisioned PostgreSQL connection."""
    settings = load_runtime_config() if config is None else config
    _validate_runtime_config(settings)
    connector: Callable[[str], _RuntimeConnection] = (
        cast(Callable[[str], _RuntimeConnection], psycopg.connect) if connect is None else connect
    )
    try:
        connection = connector(settings.dsn)
    except Exception:
        raise RuntimeError("config-service runtime database connection failed") from None

    try:
        cursor = connection.cursor()
        try:
            cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(settings.runtime_role)))
        finally:
            cursor.close()
        connection.commit()

        store_connection = cast(Any, connection)
        managed_rule_store = PostgresManagedRuleStore(
            store_connection, schema=settings.config_schema
        )
        change_order_store = PostgresChangeOrderStore(
            store_connection, schema=settings.config_schema
        )
        distribution_store = PostgresDistributionStore(
            store_connection, schema=settings.config_schema
        )
        auth_store = PostgresConsoleAuthStore(store_connection, schema=settings.config_schema)
        audit_store = PostgresAuditStore(store_connection, schema=settings.audit_schema)
        app = create_app(
            managed_rule_store=managed_rule_store,
            change_order_store=change_order_store,
            distribution_store=distribution_store,
            auth_store=auth_store,
            audit_store=audit_store,
            resolve_identity=None,
            can_read_config=_deny,
            can_submit_change=_deny,
            can_approve_change=_deny,
            can_manage_users=_deny,
            audit_resource_hmac_key=settings.audit_resource_hmac_key,
        )
        app.router.add_event_handler("shutdown", connection.close)
        return app
    except BaseException:
        _close_quietly(connection)
        raise


def main() -> int:
    """Run Uvicorn in factory mode; scheme trust must be configured at deployment."""
    try:
        settings = load_runtime_config()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    import uvicorn

    uvicorn.run(
        "as_config_service.runtime:create_runtime_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        proxy_headers=settings.proxy_headers,
        forwarded_allow_ips=",".join(settings.trusted_proxies),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
