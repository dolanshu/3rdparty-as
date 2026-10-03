# M4b-6b Audit API/Store Integration Review

## Object

Final integrated engineering review of the M4b-6b PostgreSQL audit store and config-service API behavior:

- `services/config-service/src/as_config_service/audit_store.py` and its database role/schema guards
- Request-level audit wiring and domain-write transaction coordination in `services/config-service/src/as_config_service/api.py`
- Related audit, API, and PostgreSQL integration tests
- Final evidence and status in [`acceptance/report.md`](../acceptance/report.md), [`plan.md`](../plan.md), [`hld.md`](../architecture/hld.md), [`lld.md`](../architecture/lld.md), and [`handoff/2026-09-30.md`](../handoff/2026-09-30.md)

This record reviews the final integrated engineering slice after fixes. It is not a security certification, REQ-S-4 acceptance, M4b/M4 acceptance, production deployment proof, or maintainer approval of ADR-0024.

## Date and Reviewer

- Date: 2026-10-02
- Reviewer: Independent final API/audit integration reviewer (AI)

## Conclusion

**Pass for the reviewed integrated engineering slice after fixes.** The final independent API/auth/audit review found no remaining actionable findings. M4b-6b is delivered as an engineering slice; M4b-7/8 engineering evidence progressed separately. ADR-0024 **Accepted** 2026-10-03; M4b-6b maintainer signoff recorded 2026-10-04 below. No requirement or milestone acceptance is claimed.

## Findings and Fixes

The final integrated pass found no remaining actionable findings after implementation fixes. The reviewed final behavior and controls include:

1. The durable PostgreSQL audit store uses append-only event records and canonical before/after snapshots; detail is excluded. Bounded snapshots and metadata checks reject selected credential-key/value markers and PEM private-key markers. These checks are heuristic, so producer allow-list/redaction remains necessary.
2. Explicit schema/owner setup and an allow-listed schema object catalog validate the table, constraints, triggers, and sequence. Runtime role validation enforces the intended NOLOGIN/no-CREATEROLE/no-membership shape and narrow schema/table-column/sequence grants; a separate login role must `SET ROLE` to it. These implementation checks do not prove deployment configuration.
3. Audited domain writes stage with `commit=False` and append the audit event in the same PostgreSQL transaction. Failed requests roll back domain mutations before recording DENIED with null snapshots; unavailable audit fails closed. Callback compatibility is opt-in and cannot be combined with session auth.
4. Request auditing includes allowed/denied outcomes and unmatched internal API methods, while identity, permission, and CSRF guards remain in force. Session path identifiers are stored as full HMAC-SHA256 digests over sorted parameter names, not raw path/query; the stable 32-byte key is externally provisioned, and rotation breaks cross-period correlation.
5. Distribution completion/report audit and ManagedRule plus ChangeOrder APPLIED/audit remain separate PostgreSQL transactions. No cross-transaction or distributed atomicity is claimed.

## Verification and Final Confirmation

- Latest local `make gate`: Ruff format **225 files already formatted**; Ruff clean; mypy **45 source files clean**; pytest `-m "unit or contract"`: **767 passed, 2 skipped, 131 deselected**, with 11 non-failing Starlette/httpx deprecation warnings.
- Config-service integration markers: **122 passed, 3 skipped, 404 deselected** against PostgreSQL **12.22**, with 5 deprecation warnings. Three publication DDL tests were skipped because the server uses `wal_level=replica`; those tests require `logical`.
- Latest affected workflow matrix: **264 passed, 3 skipped, 15 warnings**. Latest API/audit catchall subset: **89 passed, 15 warnings**.
- Local verification only; CI was not run. PostgreSQL 16 was not tested.
- Final independent reviewer confirmation after fixes: **no remaining actionable findings**.

## Remaining Limits

M4b-7 UI/workflow integration and M4b-8 browser acceptance are open. There is no browser login UI, application rate limiting, MFA/SSO, deployed HTTPS trusted-proxy/ingress proof, CI evidence, or PostgreSQL 16 result. The HMAC key is externally provisioned, and key rotation breaks cross-period correlation. Heuristic secret checks do not replace producer allow-list/redaction. REQ-S-4, M4b, and M4 remain unaccepted.

- Independent reviewer confirmation: 2026-10-02
- Maintainer signoff: **Approved**; recorded by AI agent per maintainer authorization in chat (2026-10-04).
