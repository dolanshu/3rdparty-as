"""Compile the first-edition rules through config-service and print the bundle.

Connects to the lab PostgreSQL (the same database config-service uses), then
drives propose, submit, approve, distribute, and activate. A second user
approves. The SIP process does not pull the bundle; the caller mounts the
JSON this script prints.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import json
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from as_config_service.api import create_app
from as_config_service.as_instance import AsInstance, AsUseCase
from as_config_service.as_instance_store import PostgresAsInstanceStore
from as_config_service.audit_store import PostgresAuditStore
from as_config_service.change_order_store import PostgresChangeOrderStore
from as_config_service.distribution_store import PostgresDistributionStore
from as_config_service.managed_rule_store import PostgresManagedRuleStore
from as_config_service.postgres_store import PostgresVersionStore

_SCHEMA = "as_config"
_AUDIT_SCHEMA = "console_audit"
_ROLE = "as_config_runtime"
_INSTANCE = "as-sut-translation"
_PROPOSER = "ops-alice"
_APPROVER = "mgr-bob"
_TARGET = "sip:uas@south"
_RULES: tuple[dict[str, object], ...] = (
    {
        "rule_id": "t1-plus86",
        "name": "T1 translate +86138",
        "match_field": "called",
        "match_mode": "prefix",
        "match_value": "+86138",
        "target_service": "translation",
        "enabled": True,
        "target_detail": _TARGET,
        "action": "translate",
    },
    {
        "rule_id": "t5-forward",
        "name": "T5 forward +15550001",
        "match_field": "called",
        "match_mode": "prefix",
        "match_value": "+15550001",
        "target_service": "routing",
        "enabled": True,
        "target_detail": _TARGET,
        "action": "forward",
    },
    {
        "rule_id": "f1-allow",
        "name": "F1 forward +15550002",
        "match_field": "called",
        "match_mode": "prefix",
        "match_value": "+15550002",
        "target_service": "routing",
        "enabled": True,
        "target_detail": _TARGET,
        "action": "forward",
    },
    {
        "rule_id": "f2-block",
        "name": "F2 block +15550003",
        "match_field": "called",
        "match_mode": "prefix",
        "match_value": "+15550003",
        "target_service": "block",
        "enabled": True,
        "target_detail": None,
        "action": "block",
    },
)


def _local_dsn(dsn: str, port: int) -> str:
    parts = urlsplit(dsn)
    if parts.username is None or parts.password is None:
        raise SystemExit("AS_CONFIG_DSN is missing a user or password")
    netloc = f"{parts.username}:{parts.password}@127.0.0.1:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _post(
    client: TestClient,
    connection: psycopg.Connection[tuple[object, ...]],
    path: str,
    body: object | None,
) -> dict[str, object]:
    response = client.post(path, json=body) if body is not None else client.post(path)
    connection.commit()
    if response.status_code not in {200, 201}:
        raise SystemExit(f"{path} -> {response.status_code} {response.text}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} returned a non-object")
    return payload


def _publish_one(
    alice: TestClient,
    bob: TestClient,
    connection: psycopg.Connection[tuple[object, ...]],
    rule: dict[str, object],
    plan_version: int,
) -> None:
    record = {key: value for key, value in rule.items() if key != "action"}
    proposed = _post(alice, connection, "/internal/v1/managed-rules", record)
    order = proposed["record"]["order"]
    if not isinstance(order, dict):
        raise SystemExit("proposal response has no order")
    change_id = str(order["change_id"])
    _post(alice, connection, f"/internal/v1/change-orders/{change_id}/submit", None)
    approved = _post(bob, connection, f"/internal/v1/change-orders/{change_id}/approve", None)
    revision = approved["revision"]
    _post(
        bob,
        connection,
        f"/internal/v1/change-orders/{change_id}/distribution",
        {
            "version": plan_version,
            "batches": [[_INSTANCE]],
            "expected_change_order_revision": revision,
        },
    )
    applied = _post(
        bob,
        connection,
        f"/internal/v1/change-orders/{change_id}/distribution/reports",
        {
            "expected_distribution_revision": 1,
            "reports": {_INSTANCE: True},
        },
    )
    change_order = applied.get("change_order")
    if not isinstance(change_order, dict):
        raise SystemExit(f"{rule['rule_id']} distribution did not activate")
    state = change_order["record"]["order"]["state"]
    if state != "applied":
        raise SystemExit(f"{rule['rule_id']} ended in {state}")


def main() -> int:
    """Publish missing first-edition rules and write the latest bundle JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--hmac-b64", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    hmac_key = base64.b64decode(args.hmac_b64)
    if len(hmac_key) != 32:
        raise SystemExit("audit hmac key must be 32 bytes")

    connection = psycopg.connect(_local_dsn(args.dsn, args.port), connect_timeout=5)
    try:
        cursor = connection.cursor()
        cursor.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(_ROLE)))
        cursor.execute(
            sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(_SCHEMA))
        )
        cursor.close()
        connection.commit()

        managed = PostgresManagedRuleStore(connection, schema=_SCHEMA)
        orders = PostgresChangeOrderStore(connection, schema=_SCHEMA)
        distribution = PostgresDistributionStore(connection, schema=_SCHEMA)
        instances = PostgresAsInstanceStore(connection, schema=_SCHEMA)
        audit = PostgresAuditStore(connection, schema=_AUDIT_SCHEMA)
        versions = PostgresVersionStore(connection, table=f"{_SCHEMA}_config_versions")

        if instances.get(_INSTANCE) is None:
            instances.create(
                AsInstance(
                    instance_id=_INSTANCE,
                    use_case=AsUseCase.TRANSLATION,
                    notify_url=None,
                    health_url=None,
                    enabled=True,
                ),
                "m71-seed",
                _PROPOSER,
                time.time(),
            )
        connection.rollback()

        def client_for(user_id: str) -> TestClient:
            identity = type("Identity", (), {"user_id": user_id})()
            return TestClient(
                create_app(
                    managed_rule_store=managed,
                    change_order_store=orders,
                    resolve_identity=lambda _request: identity,
                    can_read_config=lambda _candidate: True,
                    can_submit_change=lambda _candidate: True,
                    can_approve_change=lambda _candidate: True,
                    distribution_store=distribution,
                    version_store=versions,
                    as_instance_store=instances,
                    audit_store=audit,
                    audit_resource_hmac_key=hmac_key,
                )
            )

        alice = client_for(_PROPOSER)
        connection.rollback()
        bob = client_for(_APPROVER)
        connection.rollback()
        missing = [rule for rule in _RULES if managed.get(str(rule["rule_id"])) is None]
        history = versions.history()
        connection.rollback()
        next_version = (history[-1].version if history else 0) + 1
        for offset, rule in enumerate(missing):
            _publish_one(alice, bob, connection, rule, next_version + offset)

        latest = versions.latest()
        if latest is None:
            raise SystemExit("version store has no bundle")
        found = {rule.rule_id: rule.action for rule in latest.bundle.rules}
        expected = {str(rule["rule_id"]): str(rule["action"]) for rule in _RULES}
        if found != expected:
            raise SystemExit(f"compiled bundle rules {found} != {expected}")
        text = json.dumps(dataclasses.asdict(latest.bundle), sort_keys=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
        print(args.out)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
