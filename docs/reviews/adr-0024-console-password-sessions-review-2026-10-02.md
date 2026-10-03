# ADR-0024 Console Password Sessions Design Review

## Object

Independent design review of the proposed console role/password/PG-session boundary and corresponding HLD, LLD, plan, and test-plan changes. Reviewed artifacts: [draft ADR-0024](../architecture/adr/0024-console-password-sessions.md), [HLD](../architecture/hld.md), [LLD](../architecture/lld.md), [implementation plan](../plan.md), and [acceptance test plan](../acceptance/test-plan.md).

## Date and Reviewer

- Date: 2026-10-02
- Reviewer: Independent reviewer (AI)

## Conclusion

**Pass after fixes.** The final independent review found no remaining design mismatch. ADR-0024 is **accepted** per maintainer signoff below. This is not security certification, REQ-S-4 acceptance, or M4b/M4 acceptance.

## Findings and Fixes

1. **Stale sessions after account changes:** Every authenticated request resolves the user's current database role and enabled state. Role changes, disablement, and password changes revoke all of that user's sessions in the same transaction as the change.
2. **Bootstrap race:** Bootstrap locks the pre-existing singleton row, checks the empty user store, inserts the initial ADMIN, and marks bootstrap complete in one PostgreSQL transaction. Repeated and concurrent attempts fail.
3. **HTTPS, proxy trust, and cookie scope:** No arbitrary `Forwarded` metadata is trusted; a configured proxy must strip client-supplied forwarding headers and replace them with canonical trusted metadata. Cookies are `__Host` scoped with `Secure`, `SameSite=Strict`, `Path=/`, and no `Domain`; the session cookie is `HttpOnly`.
4. **Credential and CSRF handling:** The password verifier is versioned PBKDF2 with canonical encoding, exact UTF-8 input and no normalization or truncation, CSPRNG salt, fixed derived-key size, constant-time verification, and rehashing. The CSRF token is an unpredictable 256-bit value stored by digest only, rotated, and checked in constant time.
5. **REQ-S-4 audit contract and test-plan alignment:** Every operation requires authorization and audit with actor, time, action, resource, before/after values, and secret/header redaction. The runtime API role has no effective `UPDATE`, `DELETE`, or `TRUNCATE` on audit data and retains only required `INSERT`/`SELECT`; migrations use a separate owner role. Trigger/constraint defenses and effective privilege/denial tests are specified.

## Status and Signoff

M4b-6a auth/session and M4b-6b durable append-only audit are delivered as engineering slices on branch `cur` (see **Implementation review (2026-10-03)** below). REQ-S-4 acceptance, M4b acceptance, and M4b-8 browser evidence remain unchecked.

## Implementation review (2026-10-03)

Independent implementation review of the M4b-6a/6b slices on branch `cur` against [ADR-0024](../architecture/adr/0024-console-password-sessions.md) and the 2026-10-02 design review baseline.

### Scope and evidence

- Auth/session: [`auth.py`](../../services/config-service/src/as_config_service/auth.py), [`api.py`](../../services/config-service/src/as_config_service/api.py), [`bootstrap_admin.py`](../../services/config-service/src/as_config_service/bootstrap_admin.py); tests in [`test_auth.py`](../../services/config-service/tests/test_auth.py) and PostgreSQL integration tests.
- Durable audit: [`audit_store.py`](../../services/config-service/src/as_config_service/audit_store.py); tests in [`test_audit_store.py`](../../services/config-service/tests/test_audit_store.py) and PostgreSQL integration tests.

### Validation

- Focused gate: **104 passed** across `test_auth` and `test_audit_store` (unit and PostgreSQL integration subsets as run in the implementation review).
- **No P0 drift** from the accepted design-review fixes (session revocation on account change, bootstrap transaction, cookie/CSRF contract, verifier encoding, audit privilege model).

### Residual notes (non-blocking for impl alignment)

- **P2:** Session cookie `Max-Age` vs eight-hour absolute expiry semantics should be verified in deployment/browser evidence.
- **P2:** No dedicated session renewal endpoint; absolute lifetime only (consistent with ADR text).

### Conclusion (implementation)

**Pass for implementation alignment** with ADR-0024 and the 2026-10-02 design review. This is **not** REQ-S-4 acceptance, **not** M4b acceptance, and **not** M4b-8 browser workflow acceptance.

## Maintainer signoff

| Field | Value |
|-------|--------|
| Design review conclusion | Pass (2026-10-02) |
| Implementation review date | 2026-10-03 |
| ADR-0024 status | **Accepted** |
| Maintainer | Approved; recorded by AI agent per maintainer authorization in chat (2026-10-03) |