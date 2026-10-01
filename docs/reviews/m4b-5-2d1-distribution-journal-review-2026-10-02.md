# M4b-5-2d1 Distribution Journal Review

## Object

Engineering review of the M4b-5-2d1 PostgreSQL distribution journal implementation:

- `services/config-service/src/as_config_service/distribution_store.py`
- `services/config-service/tests/test_distribution_store.py`
- `services/config-service/tests/test_postgres_distribution_store_integration.py`

This is an engineering-slice review only. It is not a formal REQ review, M4b/M4 acceptance, or evidence of fleet delivery or activation.

## Date and Reviewer

- Date: 2026-10-02
- Reviewer: Independent reviewer (AI)

## Conclusion

**Pass for the reviewed engineering slice after fixes.** The final independent review found no remaining concrete defects in database guards, schema qualification, or the deterministic concurrency regression test.

## Findings and Fixes

1. **Head/event revision invariants were incomplete.** ChangeOrder, ManagedRule, and Distribution guards did not consistently reject a head revision below the maximum event revision. The guards were corrected across all three stores.
2. **Trigger function resolution could be shadowed through `search_path`.** Trigger functions were hardened against search-path shadowing.
3. **ChangeOrder payload identity could differ from its relational key.** The embedded change ID is now checked against the key used by the relational write.
4. **Store SQL could resolve relations through a hostile `search_path`.** All three stores now accept a validated keyword-only `schema="public"`, fully qualify SQL relation names, and do not mutate connection `search_path`. A hostile-shadow-path/custom-schema regression covers this behavior.
5. **A READ COMMITTED joined lock-read race lacked deterministic regression coverage.** A two-connection PostgreSQL test now proves the losing writer is in lock wait before the winner commits, then verifies the resulting behavior.

## Verification and Final Confirmation

- Distribution unit suite: **51 passed**.
- Distribution PostgreSQL integration suite: **8 passed** on temporary PostgreSQL **12.22**.
- Focused config-service run across ChangeOrder, ManagedRule, Distribution unit and PostgreSQL integration, plus activation integration: **156 passed** on temporary PostgreSQL 12.22 (`127.0.0.1:55432`).
- Local `make gate`: Ruff format **211 files already formatted**; Ruff all passed; mypy **42 source files clean**; pytest `-m "unit or contract"`: **636 passed, 2 skipped, 56 deselected**. One non-failing Starlette/httpx deprecation warning. Local run only; CI was not run.
- PostgreSQL 16 was not tested; this remains a nonblocking follow-up.

Final independent confirmation after repairs: **no remaining concrete findings** in the reviewed scope.

- Independent reviewer confirmation: 2026-10-02
- Maintainer signoff: **Pending**
