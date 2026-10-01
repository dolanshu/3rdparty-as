# M4b-5-2c APPLIED Transaction Coordination Engineering Review

Date: 2026-10-01
Scope: `services/config-service/src/as_config_service/activation.py`, `managed_rule_store.py`, `change_order_store.py`, and `services/config-service/tests/test_postgres_activation_integration.py`
Status: final independent activation review found no findings after the idle-connection guard was added; maintainer signoff pending.

## Scope and contract

This review covers the transaction slice that coordinates a typed `CREATE`, `UPDATE`, or `DELETE` `ManagedRuleChange` with a ChangeOrder transition to `APPLIED`. It is engineering evidence only, **not M4b or M4 acceptance**, and no REQ is accepted by this review.

## Transaction invariants

- `apply_distributed_change` uses the same psycopg connection for the ManagedRuleStore create/append and ChangeOrderStore `append_transition` operations. Both store operations use `commit=False`; one commit occurs after both writes. Errors roll back the transaction.
- Before reads or writes, the function verifies exact connection identity and checks that `psycopg` transaction status is `IDLE`.
- The caller must exclusively own that idle connection for the entire call. The precondition does not provide coordination across hosts or callers that bypass exclusive ownership.
- The transaction is local to PostgreSQL. It does not establish global, cross-host, failover, or distributed atomicity, and it does not include delivery to the active fleet.

## Verification and review result

- The activation integration file contains seven integration cases. Coverage includes CREATE, UPDATE, DELETE, the legacy no-proposal path, the different-connection guard, and a stale ChangeOrder revision after a provisional ManagedRule write, checking that both stores roll back.
- Latest config-service integration run on PostgreSQL **12.22**: **37 passed, 216 deselected**. PostgreSQL 16 compatibility remains an unverified, nonblocking follow-up.
- Latest local `make gate`: Ruff format **207 files formatted**, Ruff clean, mypy **41 source files clean**, pytest **577 passed, 2 known skips, 43 deselected**, with one non-failing Starlette warning. Local only; CI was not run.
- The independent activation reviewer reported no findings after the idle-connection guard was added.

## Residual gaps and boundaries

This code slice coordinates two writes in one PostgreSQL transaction only. It is not proof of distribution success, active-fleet convergence, SIP runtime behavior, D10 recovery, or M4b/M4 acceptance. M4b-5-2b remains journal-only; the next step is M4b-5-2d, connecting the actual distribution result to the `APPLIED` API path and exposing observed status. M4b-6 auth/session/audit, M4b-7 UI integration, and M4b-8 browser acceptance remain pending. No REQ acceptance is claimed.

Maintainer signoff: pending.