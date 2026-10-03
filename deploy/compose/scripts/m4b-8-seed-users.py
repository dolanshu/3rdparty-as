"""Dev-only: align compose console users for M4b-8 Playwright evidence (owner DSN)."""

from __future__ import annotations

import os
import sys
import time

from as_config_service.auth import (
    DuplicateConsoleUserError,
    PostgresConsoleAuthStore,
)
from as_console.access import Role


def main() -> int:
    dsn = os.environ.get("AS_CONFIG_OWNER_DSN")
    if not dsn:
        print("AS_CONFIG_OWNER_DSN must be set.", file=sys.stderr)
        return 1
    password = os.environ.get("M4B8_E2E_PASSWORD")
    if not password or len(password) < 12:
        print("M4B8_E2E_PASSWORD must be at least 12 characters.", file=sys.stderr)
        return 1
    schema = os.environ.get("AS_CONFIG_SCHEMA", "as_config")

    import psycopg

    connection = psycopg.connect(dsn)
    store = PostgresConsoleAuthStore(connection, schema=schema)
    now = time.time()
    store.update_user("admin", now, password=password)
    for user_id, roles in (
        ("ops-e2e", frozenset({Role.OPERATOR})),
        ("mgr-e2e", frozenset({Role.APPROVER})),
    ):
        try:
            store.create_user(user_id, password, roles, now)
        except DuplicateConsoleUserError:
            store.update_user(user_id, now, password=password, roles=roles)
    connection.commit()
    connection.close()
    print("M4b-8 e2e users ready (admin, ops-e2e, mgr-e2e).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
