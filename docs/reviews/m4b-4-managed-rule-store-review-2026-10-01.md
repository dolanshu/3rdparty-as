# M4b-4 ManagedRule Store Review

> Date: 2026-10-01
> Review type: implementation review; engineering evidence only, not milestone acceptance
> Reviewer: independent reviewer (final review)
> Maintainer signoff: pending

## Scope And Spec

Reviewed the M4b-4 PostgreSQL ManagedRule persistence slice against its append-only management-plane persistence scope and the current M4b requirements context. This review does not accept M4b-4 as M4b/M4 completion and does not constitute requirement acceptance.

- [`managed_rule_store.py`](../../services/config-service/src/as_config_service/managed_rule_store.py)
- [`test_managed_rule_store.py`](../../services/config-service/tests/test_managed_rule_store.py)
- [`test_postgres_managed_rule_store_integration.py`](../../services/config-service/tests/test_postgres_managed_rule_store_integration.py)
- [`managed_rule.py`](../../services/config-service/src/as_config_service/managed_rule.py)
- [`test-plan.md`](../acceptance/test-plan.md)
- [`prd.md`](../requirements/prd.md)
- [`report.md`](../acceptance/report.md)

## Reviewed Invariants

The store persists append-only ManagedRule snapshots and tombstones using schema-v1 JSON. Revision updates use row locking and compare-and-swap. The schema uses a deferred head/event foreign key, database protection against event UPDATE/DELETE/TRUNCATE, and a prefix-scoped safe guard function. Audit data includes actor/change metadata and finite timestamp checks.

This remains management-plane persistence only. It does not provide runtime RuleDTO mapping, regex compilation, HTTP API, authentication/session, or UI workflow.

## Findings And Fixes

The independent review raised findings concerning TRUNCATE protection, Unicode audit metadata, and the PostgreSQL version assertion. These were fixed. The final M4b-4 review reported no findings.

## Validation And Residual Risk

The focused `test_managed_rule_store.py` (unit) and `test_postgres_managed_rule_store_integration.py` runs passed **38 tests total**. Only the integration subset (**6 parametrized cases**) ran against temporary PostgreSQL **12.22**; the 38 total must not be read as database-backed tests. Integration coverage includes create/update/delete history and tombstones, CAS/duplicate behavior, rejection of event UPDATE/DELETE/TRUNCATE, deferred-FK rollback, and the PostgreSQL >=12 guard.

Latest main-agent full gate (local; CI was not run): Ruff format **200 files formatted**; Ruff clean; mypy **39 source files clean**; pytest **506 passed, 2 known skips, 36 deselected**. Config-service integration markers on PostgreSQL 12.22 additionally yielded **30 passed, 145 deselected**.

The temporary PostgreSQL 12.22 server was extracted from Ubuntu debs under `/tmp/as-m4b-postgres`, bound to loopback only, and stopped after use. No system packages were installed. PostgreSQL **16 compatibility remains unverified** and is a non-blocking follow-up.

## Conclusion

**Pass for the tested PostgreSQL 12.22 M4b-4 persistence slice only.** PostgreSQL 16 compatibility remains an open, non-blocking follow-up; maintainer signoff is pending. This is not M4b or M4 acceptance, and no REQ acceptance is claimed. M4b-5 remains the next substep: internal HTTP API and validation/error mapping built on both durable stores. Authentication/session and UI workflow acceptance remain outstanding.