# M4b-5-2d2 Distribution API Review

## Object

Engineering review of the M4b-5-2d2 distribution API/report-to-activation slice:

- Distribution routes and request-level serialization in `services/config-service/src/as_config_service/api.py`
- API and PostgreSQL activation/distribution integration tests

This is an engineering-slice review only. It is not a REQ review, M4b/M4 acceptance, or evidence of AS notification, fleet delivery, runtime version loading, or health attestation.

## Date and Reviewer

- Date: 2026-10-02
- Reviewer: Independent reviewer (AI)

## Conclusion

**Pass for the reviewed engineering slice after fixes.** The final independent review found no actionable findings.

## Findings and Fixes

1. **P1: Concurrent requests could share a connection transaction.** Added app-scoped request serialization across both routers, an idle/pre-existing-transaction guard, and cleanup. The injected PostgreSQL connection must be dedicated to the app and must not be shared externally.
2. **P2: An exact `/apply` retry using the original revision could fail as stale.** The API now accepts only an exact prior `APPLIED` transition matching actor, expected-plus-one revision, and final `mark_applied` audit action; unrelated stale requests still return 409.

## Verification and Final Confirmation

- Focused API, activation, and distribution PostgreSQL tests: **79 passed**, with one existing Starlette/httpx deprecation warning.
- Full config-service integration command: **61 passed, 280 deselected** on temporary PostgreSQL **12.22**. PostgreSQL 16 was not tested; this is a nonblocking follow-up.
- Latest local `make gate`: Ruff format **212 files already formatted**; Ruff clean; mypy **42 source files clean**; pytest `-m "unit or contract"`: **641 passed, 2 skipped, 67 deselected**. One non-failing Starlette/httpx deprecation warning. Local only; CI was not run.
- The API uses an injected `can_approve_change` permission seam, not a real auth provider/session. It accepts reports but has no AS notifier/transport or proof that an AS loaded the reported version, and no real health attestation. Distribution completion and ManagedRule/ChangeOrder `APPLIED` coordination are separate committed PostgreSQL transactions; there is no global/distributed atomicity claim.

Final independent confirmation after repairs: **no actionable findings** in the reviewed engineering slice.

- Independent reviewer confirmation: 2026-10-02
- Maintainer signoff: **Pending**