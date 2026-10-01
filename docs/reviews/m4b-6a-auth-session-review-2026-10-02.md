# M4b-6a Console Auth and Session Review

## Object

Engineering review of the M4b-6a role/password/session implementation:

- `services/config-service/src/as_config_service/auth.py`, `api.py`, and `bootstrap_admin.py`
- `services/config-service/tests/test_api.py`, `test_auth.py`, `test_postgres_auth_integration.py`, and `test_postgres_auth_api_integration.py`
- Design and implementation-status documentation: [draft ADR-0024](../architecture/adr/0024-console-password-sessions.md), [HLD](../architecture/hld.md), [LLD](../architecture/lld.md), [plan](../plan.md), and [acceptance evidence](../acceptance/report.md)

This is an engineering-slice review only. It is not security certification, REQ-S-4 acceptance, M4b/M4 acceptance, or maintainer approval of ADR-0024.

## Date and Reviewer

- Date: 2026-10-02
- Reviewer: Independent auth/core and API reviewer (AI)

## Conclusion

**Pass for the reviewed engineering slice after fixes.** The final independent review found no remaining concrete findings. ADR-0024 remains draft pending maintainer review/signoff. No requirement or milestone acceptance is claimed.

## Findings and Fixes

The implementation was reviewed after its fixes. The final reviewer reported no remaining concrete findings; no unresolved code finding is carried by this record. The final review covered the password/session core and API wiring, including the following documented invariants:

1. Session authentication is primary and fail-closed when configured; the backwards-compatible injected callback mode does not serve as a fallback after failed session authentication.
2. Password verification uses the specified PBKDF2-HMAC-SHA256 parameters and exact UTF-8 input, with no normalization/truncation, maximum input length enforcement, and constant-time digest comparison. Session and CSRF bearer values are random, digest-only at rest, and have bounded absolute session lifetime.
3. Current enabled account roles are resolved per request. Role/password/disable mutations revoke sessions transactionally; one-time admin bootstrap is singleton-locked; user management protects the last enabled administrator.
4. HTTPS login enforcement, `__Host-` cookie attributes, CSRF checks on writes, and existing RBAC integration are part of the reviewed API behavior.

Contract and residual boundaries: auth stores use dedicated injected PostgreSQL connections. An error rolls back the entire active transaction even when `commit=False`. The app-scoped request lock protects a shared connection only within one process; it is not a cross-process lock. These are documented operating constraints, not claims of database privilege separation or distributed serialization.

## Verification and Final Confirmation

- Focused API/auth/store command (`test_api.py`, `test_auth.py`, `test_postgres_auth_integration.py`, `test_postgres_auth_api_integration.py`): **116 passed**, with 11 non-failing Starlette/httpx warnings.
- Full config-service integration command: **85 passed, 319 deselected** against PostgreSQL **12.22**. PostgreSQL 16 was not tested.
- Current local `make gate`: Ruff format **220 files already formatted**; Ruff clean; mypy **44 source files clean**; pytest `-m "unit or contract"`: **680 passed, 2 skipped, 91 deselected**. Eight non-failing Starlette/httpx deprecations (one base warning and TestClient per-request cookie warnings). Local only; CI was not run.
- Final independent reviewer confirmation after fixes: **no remaining concrete findings**.

Not verified or not implemented by this slice: PostgreSQL 16 compatibility; deployed trusted-proxy/ingress behavior; database runtime-role least privilege; application rate limiting; durable append-only audit; browser login UI and browser acceptance. Login checks the ASGI `request.url.scheme`; this is not proof of production proxy configuration. Since durable audit is absent, authorization decisions and all accesses are not durably audited until M4b-6b. ADR-0024 remains draft; REQ-S-4, M4b, and M4 remain unaccepted.

- Independent reviewer confirmation: 2026-10-02
- Maintainer signoff: **Pending**