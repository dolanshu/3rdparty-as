"""Unit coverage for fleet instance inventory validation."""

from __future__ import annotations

import pytest

from as_config_service.as_instance import AsInstance, AsUseCase
from as_config_service.as_instance_store import PostgresAsInstanceStore

pytestmark = pytest.mark.unit


def test_postgres_as_instance_store_rejects_unsafe_schema_names() -> None:
    with pytest.raises(ValueError, match="schema"):
        PostgresAsInstanceStore(object(), schema="public-evil")


def test_create_rejects_invalid_urls() -> None:
    store = PostgresAsInstanceStore(_FakeConnection(), schema="as_config")
    instance = AsInstance(
        instance_id="as-1",
        use_case=AsUseCase.TRANSLATION,
        notify_url="ftp://bad",
        health_url=None,
        enabled=True,
    )

    with pytest.raises(ValueError, match="notify_url"):
        store.create(instance, "change-1", "ops", 1.0, commit=False)


class _FakeCursor:
    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        raise AssertionError("database not expected in validation-only test")

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        return []


class _FakeConnection:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def commit(self) -> None:
        raise AssertionError("commit not expected")

    def rollback(self) -> None:
        pass
