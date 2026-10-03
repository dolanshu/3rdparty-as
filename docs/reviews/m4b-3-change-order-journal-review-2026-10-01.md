# M4b-3 Change-Order Journal Review

> Date: 2026-10-01
> Review type: implementation review; not milestone acceptance
> Maintainer signoff: Approved; recorded by AI agent per maintainer authorization in chat (2026-10-04).

## Scope

Reviewed the M4b-3 change-order journal implementation and its unit and PostgreSQL integration tests against the change-order invariants and the current M4b requirements context. This review does not accept M4b-3 as complete and does not constitute M4b or M4 acceptance.

- [`change_order_store.py`](../../services/config-service/src/as_config_service/change_order_store.py)
- [`test_change_order_store.py`](../../services/config-service/tests/test_change_order_store.py)
- [`test_postgres_change_order_store_integration.py`](../../services/config-service/tests/test_postgres_change_order_store_integration.py)
- [`change_order.py`](../../services/config-service/src/as_config_service/change_order.py)
- [`test-plan.md`](../acceptance/test-plan.md)
- [`prd.md`](../requirements/prd.md)
- [`report.md`](../acceptance/report.md)

## Implementation Evidence

The store implements an append-only PostgreSQL change-order journal with strict versioned JSON snapshots, head-revision compare-and-swap/row locking, a deferred head-to-event foreign key, a database trigger prohibiting event UPDATE/DELETE, and a prefix-scoped safe guard function. It validates the complete legal state transition and exactly one audit append. Blank reject and rollback reasons are rejected by the pure state machine.

The newest focused `test_change_order_store.py` run passed **9 tests**. Existing change-order tests now cover blank reason cases. An earlier focused combined run passed **44 tests** with **2 integration skips**. The PostgreSQL integration module contains two cases for append/CAS/history and database constraints.

## Findings And Fixes

The independent review identified inconsistent handling of blank reject/rollback reasons, plus database immutability, head-FK, skip-reporting, and cleanup issues. The implementation fixes were applied. The final reviewer reported no implementation findings on the invariants. That reviewer recommended a persistence-validator test for a blank rollback reason; the test was added and separately reviewed with no findings.

## Validation And Residual Risk

Latest focused unit run: **9 passed**. Latest local `make gate`: Ruff format reported 197 files; Ruff clean; mypy reported 38 source files clean; pytest **463 passed, 2 known skips, 21 deselected**. This is local evidence only; CI was not run.

The PostgreSQL integration command `AS_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/as_config uv run pytest -q services/config-service/tests/test_postgres_change_order_store_integration.py` passed **6 cases** against a temporary PostgreSQL **12.22** server (two integration test functions, six parametrized cases). The server bound only to loopback; data and logs were under `/tmp/as-m4b-postgres`; it was stopped after use. PostgreSQL packages were extracted under `/tmp` without installing system packages, and no user or production database was touched. PostgreSQL **16 compatibility remains unverified** and is a non-blocking follow-up; this PG12.22 result is not PG16 or deployment acceptance.

## Conclusion

**Conditional pass for the exercised M4b-3 PostgreSQL 12.22 slice; PG16 compatibility remains open.** The integration evidence verifies the exercised database behavior, while PostgreSQL 16 compatibility remains a non-blocking follow-up. Maintainer signoff recorded 2026-10-04 (chat authorization). This is implementation groundwork only: there is no HTTP API, ManagedRule persistence, authentication/session, UI integration, or M4b acceptance; no REQ acceptance is claimed. Overall M4b and M4 remain open.