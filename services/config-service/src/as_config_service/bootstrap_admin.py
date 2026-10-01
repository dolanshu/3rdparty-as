"""Interactive one-time first-administrator bootstrap command. See ADR-0024."""

from __future__ import annotations

import getpass
import hmac
import os
import sys
import time

from as_config_service.auth import BootstrapAlreadyCompleteError, PostgresConsoleAuthStore


def main() -> int:
    """Prompt for first-admin credentials and persist them using a temporary connection."""
    dsn = os.environ.get("AS_CONFIG_DSN")
    if not dsn:
        print("AS_CONFIG_DSN must be set.", file=sys.stderr)
        return 1

    user_id = input("First administrator user ID: ")
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not hmac.compare_digest(password.encode("utf-8"), confirmation.encode("utf-8")):
        print("Passwords do not match.", file=sys.stderr)
        return 1

    connection = None
    try:
        import psycopg

        connection = psycopg.connect(dsn)
        store = PostgresConsoleAuthStore(connection)
        store.ensure_schema()
        store.bootstrap_admin(user_id, password, time.time())
    except BootstrapAlreadyCompleteError:
        print("First administrator bootstrap is unavailable.", file=sys.stderr)
        return 1
    except Exception:
        print("First administrator bootstrap failed.", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()

    print("First administrator created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
