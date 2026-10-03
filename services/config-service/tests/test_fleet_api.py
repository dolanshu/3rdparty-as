"""API coverage for fleet inventory and distribution integration."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any
from urllib.request import Request

import pytest
from fastapi import Request as FastAPIRequest
from fastapi.testclient import TestClient

from as_config_service.api import ApiIdentity, create_app
from as_config_service.as_instance import AsInstance, AsUseCase
from as_config_service.as_instance_store import StoredAsInstance
from as_config_service.change_order import ChangeOrder, ChangeState
from as_config_service.change_order_store import StoredChangeOrder
from as_config_service.distribution_store import StoredDistribution
from as_config_service.distributor import Distribution, DistributionPlan, DistributionState, begin
from as_config_service.managed_rule_store import StoredManagedRule
from as_platform.api.contract import ConfigBundle

pytestmark = pytest.mark.unit

_NOW = 1_700_000_000.0
_AUDIT_KEY = b"f" * 32


class _HttpOk:
    def __init__(self, body: bytes = b"") -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return 200

    def __enter__(self) -> _HttpOk:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@dataclass(frozen=True)
class Identity:
    user_id: str


class FakeAsInstanceStore:
    def __init__(self, records: tuple[StoredAsInstance, ...]) -> None:
        self.records = {item.instance.instance_id: item for item in records}

    def create(
        self,
        instance: AsInstance,
        change_id: str,
        actor: str,
        updated_at: float,
        *,
        commit: bool = True,
    ) -> StoredAsInstance:
        stored = StoredAsInstance(instance, 1, change_id, actor, updated_at)
        self.records[instance.instance_id] = stored
        return stored

    def get(self, instance_id: str) -> StoredAsInstance | None:
        return self.records.get(instance_id)

    def list_all(self) -> tuple[StoredAsInstance, ...]:
        return tuple(self.records[key] for key in sorted(self.records))

    def update(
        self,
        instance: AsInstance,
        change_id: str,
        actor: str,
        updated_at: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> StoredAsInstance:
        current = self.records[instance.instance_id]
        stored = StoredAsInstance(instance, current.revision + 1, change_id, actor, updated_at)
        self.records[instance.instance_id] = stored
        return stored

    def delete(
        self,
        instance_id: str,
        change_id: str,
        actor: str,
        updated_at: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> None:
        del self.records[instance_id]


class FakeDistributionStore:
    def __init__(self, stored: StoredDistribution | None = None) -> None:
        self.stored = stored
        self.create_calls = 0
        self.record_calls = 0
        self.connection = _FakeConnection()

    def get(self, change_id: str) -> StoredDistribution | None:
        return self.stored

    def create(
        self, plan: DistributionPlan, actor: str, created_at: float, *, commit: bool = True
    ) -> StoredDistribution:
        self.create_calls += 1
        distribution = replace(begin(plan), updated_at=created_at)
        self.stored = StoredDistribution(distribution, 1, actor, "begin")
        return self.stored

    def record_batch(
        self,
        change_id: str,
        reports: dict[str, bool],
        actor: str,
        now: float,
        expected_revision: int,
        *,
        commit: bool = True,
    ) -> StoredDistribution:
        self.record_calls += 1
        assert self.stored is not None
        from as_config_service.distributor import apply_batch

        distribution = replace(apply_batch(self.stored.distribution, reports, now), updated_at=now)
        self.stored = StoredDistribution(
            distribution, self.stored.revision + 1, actor, "batch_result"
        )
        return self.stored


class _FakeConnection:
    def __init__(self) -> None:
        from psycopg.pq import TransactionStatus

        self.info = type("Info", (), {"transaction_status": TransactionStatus.IDLE})()

    def rollback(self) -> None:
        return None

    def commit(self) -> None:
        return None


def _instance(
    instance_id: str = "as-1",
    *,
    notify_url: str | None = "http://notify.test/hook",
    health_url: str | None = None,
    enabled: bool = True,
) -> StoredAsInstance:
    return StoredAsInstance(
        AsInstance(
            instance_id=instance_id,
            use_case=AsUseCase.TRANSLATION,
            notify_url=notify_url,
            health_url=health_url,
            enabled=enabled,
        ),
        revision=1,
        change_id="inv-1",
        actor="ops",
        updated_at=_NOW,
    )


def _approved_order() -> StoredChangeOrder:
    order = ChangeOrder(
        change_id="change-1",
        state=ChangeState.APPROVED,
        bundle=ConfigBundle(version="v1", rules=(), toggles=()),
        created_by="ops-alice",
        created_at=_NOW,
    )
    return StoredChangeOrder(order=order, revision=2)


def _distributing_order() -> StoredChangeOrder:
    order = ChangeOrder(
        change_id="change-1",
        state=ChangeState.DISTRIBUTING,
        bundle=ConfigBundle(version="v1", rules=(), toggles=()),
        created_by="ops-alice",
        created_at=_NOW,
    )
    return StoredChangeOrder(order=order, revision=3)


def _client(
    *,
    as_instances: FakeAsInstanceStore,
    distribution: FakeDistributionStore | None = None,
    notify_opener: Callable[..., Any] | None = None,
    health_opener: Callable[..., Any] | None = None,
    order: StoredChangeOrder | None = None,
) -> TestClient:
    def resolve_identity(request: FastAPIRequest) -> ApiIdentity:
        return Identity("ops-bob")

    app = create_app(
        managed_rule_store=_EmptyRuleStore(),
        change_order_store=_OrderStore(order or _approved_order()),
        resolve_identity=resolve_identity,
        can_read_config=lambda _: True,
        can_approve_change=lambda _: True,
        distribution_store=distribution,
        as_instance_store=as_instances,
        allow_unaudited_callback_mode=True,
        fleet_notify_opener=notify_opener,
        fleet_health_opener=health_opener,
    )
    return TestClient(app)


class _EmptyRuleStore:
    def list_latest(self) -> tuple[StoredManagedRule, ...]:
        return ()

    def get(self, rule_id: str) -> None:
        return None

    def create(self, *args: object, **kwargs: object) -> StoredManagedRule:
        raise AssertionError("unexpected")

    def append(self, *args: object, **kwargs: object) -> StoredManagedRule:
        raise AssertionError("unexpected")

    def history(self, rule_id: str) -> tuple[StoredManagedRule, ...]:
        return ()


class _OrderStore:
    def __init__(self, stored: StoredChangeOrder) -> None:
        self.stored = stored

    def get(self, change_id: str) -> StoredChangeOrder | None:
        return self.stored

    def append_transition(
        self, order: ChangeOrder, expected_revision: int, *, commit: bool = True
    ) -> StoredChangeOrder:
        self.stored = StoredChangeOrder(order=order, revision=self.stored.revision + 1)
        return self.stored

    def create(self, *args: object, **kwargs: object) -> StoredChangeOrder:
        raise AssertionError("unexpected")

    def list_latest(self) -> tuple[StoredChangeOrder, ...]:
        return (self.stored,)

    def history(self, change_id: str) -> tuple[StoredChangeOrder, ...]:
        return ()


def test_list_as_instances_requires_inventory_store() -> None:
    client = _client(as_instances=FakeAsInstanceStore(()))
    response = client.get("/internal/v1/as-instances")
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_update_as_instance_inventory_row() -> None:
    store = FakeAsInstanceStore(())
    client = _client(as_instances=store)

    create = client.post(
        "/internal/v1/as-instances",
        json={
            "instance_id": "as-new",
            "use_case": "translation",
            "notify_url": "http://notify.test/hook",
            "health_url": "http://health.test/status",
            "enabled": True,
        },
    )
    assert create.status_code == 201
    created = create.json()
    assert created["instance_id"] == "as-new"
    assert created["revision"] == 1

    update = client.put(
        "/internal/v1/as-instances/as-new",
        json={
            "instance_id": "as-new",
            "use_case": "anti-fraud",
            "notify_url": "http://notify.test/hook",
            "health_url": "http://health.test/status",
            "enabled": False,
            "expected_revision": created["revision"],
        },
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["use_case"] == "anti-fraud"
    assert updated["enabled"] is False
    assert updated["revision"] == 2


def test_start_distribution_notifies_first_batch() -> None:
    notify_calls: list[Request] = []

    def notify_opener(request: Request, *, timeout: float) -> _HttpOk:
        notify_calls.append(request)
        return _HttpOk()

    distribution = FakeDistributionStore()
    client = _client(
        as_instances=FakeAsInstanceStore((_instance(),)),
        distribution=distribution,
        notify_opener=notify_opener,
    )

    response = client.post(
        "/internal/v1/change-orders/change-1/distribution",
        json={
            "version": 4,
            "batches": [["as-1"], ["as-2"]],
            "expected_change_order_revision": 2,
        },
    )

    assert response.status_code == 201
    assert distribution.create_calls == 1
    assert len(notify_calls) == 1
    assert json.loads(notify_calls[0].data.decode("utf-8")) == {
        "change_id": "change-1",
        "version": 4,
        "bundle_version": "4",
    }


def test_start_distribution_rejects_missing_inventory_member() -> None:
    client = _client(
        as_instances=FakeAsInstanceStore(()),
        distribution=FakeDistributionStore(),
    )

    response = client.post(
        "/internal/v1/change-orders/change-1/distribution",
        json={
            "version": 4,
            "batches": [["as-missing"]],
            "expected_change_order_revision": 2,
        },
    )

    assert response.status_code == 422


def test_report_distribution_validates_health_probe_match() -> None:
    distribution = Distribution(
        plan=DistributionPlan(change_id="change-1", version=4, batches=(("as-1",), ("as-2",))),
        state=DistributionState.IN_PROGRESS,
        completed_batches=0,
        reports=(),
        updated_at=_NOW,
    )
    store = FakeDistributionStore(StoredDistribution(distribution, 1, "ops", "begin"))

    def health_opener(request: Request, *, timeout: float) -> _HttpOk:
        return _HttpOk(json.dumps({"healthy": False}).encode("utf-8"))

    client = _client(
        as_instances=FakeAsInstanceStore((_instance(health_url="http://health.test/status"),)),
        distribution=store,
        health_opener=health_opener,
        order=_distributing_order(),
    )

    mismatch = client.post(
        "/internal/v1/change-orders/change-1/distribution/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": True}},
    )
    assert mismatch.status_code == 409

    def healthy_opener(request: Request, *, timeout: float) -> _HttpOk:
        return _HttpOk(json.dumps({"healthy": True}).encode("utf-8"))

    aligned_store = FakeDistributionStore(StoredDistribution(distribution, 1, "ops", "begin"))
    aligned_client = _client(
        as_instances=FakeAsInstanceStore((_instance(health_url="http://health.test/status"),)),
        distribution=aligned_store,
        health_opener=healthy_opener,
        order=_distributing_order(),
    )
    aligned = aligned_client.post(
        "/internal/v1/change-orders/change-1/distribution/reports",
        json={"expected_distribution_revision": 1, "reports": {"as-1": True}},
    )
    assert aligned.status_code == 200
    assert aligned_store.record_calls == 1
