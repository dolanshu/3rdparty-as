# M4b-5-2b ChangeOrder Journal Write API Engineering Review

Date: 2026-10-01
Scope: `services/config-service/src/as_config_service/api.py` and `services/config-service/tests/test_api.py`
Status: final independent review found no findings; maintainer signoff recorded 2026-10-04 (chat authorization).

## Scope and contract

This review covers the journal-only write API slice: draft creation, submission, approval, and rejection. The API writes ChangeOrder journal snapshots only. It does not update the active ManagedRuleStore, apply runtime rules, distribute a ConfigBundle, or provide cross-store atomicity. This is engineering evidence only, **not M4b/M4 acceptance**, and no REQ is accepted by this review.

## Endpoint and security behavior

- `POST /internal/v1/change-orders` creates a draft. Identity, submit permission, timestamp, and change ID are supplied through `create_app` injection points.
- `POST /internal/v1/change-orders/{change_id}/submit` requires the submit permission and permits only the creator to submit.
- `POST /internal/v1/change-orders/{change_id}/approve` requires the separate approve permission and rejects approval by the submitter.
- `POST /internal/v1/change-orders/{change_id}/reject` requires approve permission and a nonblank rejection reason.
- Transitions append a journal snapshot using the expected revision; validation, missing records, conflicts, and storage failures are mapped to API errors.

The injected identity and authorization callbacks are integration seams, not an authentication provider, login flow, or session implementation. Persistent console audit is not implemented. The browser/UI remains unconnected.

## Verification and review result

- Focused write API tests at the M4b-5-2b slice: **48 passed**. These use fake stores; route-level PostgreSQL CAS and concurrent API clients exercising PostgreSQL CAS were not tested. Later API coverage expanded.
- Config-service integration markers on PostgreSQL **12.22** at this slice: **30 passed, 216 deselected**, including durable stores. PostgreSQL 16 compatibility is a nonblocking, unverified follow-up.
- Historical local `make gate` snapshot at this slice: Ruff format **204 files**; Ruff clean; mypy **40 source files clean**; pytest **577 passed, 2 known skips, 36 deselected**, with one non-failing warning. Local only; CI was not run. Current gate evidence is captured in the M4b-5-2c review and handoff.
- The independent final reviewer reported no findings. The TestClient run emitted one non-failing Starlette/httpx deprecation warning.

## Residual gaps and next step

No test currently covers concurrent API clients against PostgreSQL CAS through these routes. Authentication provider/login/session, persistent console audit, browser/UI integration, and cross-store atomicity remain absent. At this slice, M4b-5-2c was next: design and implement a shared PostgreSQL transaction coordinating the active ManagedRule snapshot with the ChangeOrder `APPLIED` transition before claiming consistency. M4b and M4 remain incomplete; M4b-6 auth/session/audit, M4b-7 UI integration, and M4b-8 acceptance remain pending.

Maintainer signoff: Approved; recorded by AI agent per maintainer authorization in chat (2026-10-04).