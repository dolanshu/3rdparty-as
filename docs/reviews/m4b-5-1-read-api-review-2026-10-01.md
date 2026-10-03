# M4b-5-1 Read-Only API Engineering Review

Date: 2026-10-01
Scope: `services/config-service/src/as_config_service/api.py` and `services/config-service/tests/test_api.py`
Status: final independent review found no findings; maintainer signoff recorded 2026-10-04 (chat authorization).

## Scope and routes

The slice exposes read-only endpoints backed by injected durable stores:

- `GET /internal/v1/managed-rules`
- `GET /internal/v1/managed-rules/{rule_id}`
- `GET /internal/v1/change-orders`
- `GET /internal/v1/change-orders/{change_id}`

Each data route requires an identity from the injected identity resolver and permission from the injected config read authorizer. Missing identity returns 401; denied permission returns 403. Detail misses return 404. Path IDs are length- and control-character-validated. Pydantic nested response models explicitly mirror the schema-versioned serialized ManagedRule and ChangeOrder records. Tombstone detail returns a null rule and its revision. Docs and OpenAPI endpoints remain disabled until an actual authentication scheme exists.

## Review findings and resolution

The initial review identified documentation/OpenAPI exposure, free-form response schema, tombstone detail behavior, and Unicode control characters in path validation. Fixes were applied. The final reviewer reported no findings.

## Verification

- `services/config-service/tests/test_api.py`: **28 passed** in the latest focused run, covering authorization, list/detail, tombstone, 404, path length and Unicode controls, and valid `@` / hyphen IDs.
- Config-service integration markers on temporary PostgreSQL **12.22**: **30 passed, 145 deselected**, including both durable stores. PostgreSQL 16 compatibility remains a nonblocking follow-up.
- Latest local `make gate`: Ruff format **203 files formatted**; Ruff clean; mypy **40 source files clean**; pytest **534 passed, 2 known skips, 36 deselected**. Local evidence only; CI was not run.
- One non-failing Starlette TestClient deprecation warning recommends httpx2. Record as a tooling follow-up; no dependency was added in this documentation-only slice.

## Boundaries and follow-up

Runtime rule DTO mapping and regex compilation, write routes, change-order submission/approval/rollback API, auth provider/login/session integration, persisted console audit, and UI connection are not implemented. M4b-5 remains open. Next is M4b-5-2: design and implement ManagedRule plus change-order proposal/action write governance; do not assume cross-store atomicity before its consistency strategy is designed. This review is engineering evidence only, not M4b/M4 completion or requirement acceptance.

Maintainer signoff: Approved; recorded by AI agent per maintainer authorization in chat (2026-10-04).