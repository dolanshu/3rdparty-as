"""The PostgreSQL configuration version repository: immutable rows, append only.

ADR-0006 makes every configuration an immutable row in PostgreSQL: a new version
is appended, an old version is never updated, overwritten or deleted, and diff
and rollback are both computed from those rows. ADR-0007 assigns governance data
to PostgreSQL and runtime state to Redis, so this module is the governance side
of that split. It is the production implementation of the ``VersionStore`` seam
declared in ``as_config_service.version_store``, and a drop-in replacement for
the in-memory one: same methods, same semantics, and the caller cannot tell the
two apart.

**Immutability is the whole point.** This repository never issues an ``UPDATE``
and never issues a ``DELETE`` against a version row: the only statements it
sends are one ``CREATE TABLE IF NOT EXISTS``, one ``INSERT`` and some ``SELECT``s.
A rollback is therefore not "writing the old value back" — it is reading the
previous row, which is still there because nothing ever removed it. See ADR-0006.

The version number is the database's, not the process's: ``append`` derives it in
the same statement that writes the row (``INSERT ... SELECT COALESCE(MAX(version),
0) + 1 FROM ...``), so two processes appending concurrently cannot both claim the
same number and a restarted process cannot forget where the history ended. See
ADR-0006.

Purity: no clock is read here. ``created_at`` is a parameter of ``append``, so a
version's timestamp is a fact the caller owns, not something the repository
invents (AGENT.md §5). The connection is injected too — the caller opens it and
owns its transaction — so this module opens no socket of its own and can be used
against any DB-API connection. The PostgreSQL driver itself is imported lazily by
``from_dsn``, which keeps this module importable on a host without the driver.
See ADR-0006, ADR-0007.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any, Protocol

from as_config_service.version_store import ConfigVersion
from as_platform.api.contract import ConfigBundle, RuleDTO, ToggleDTO

DEFAULT_TABLE = "config_versions"

# A table name cannot be a bound parameter in SQL, so it is interpolated; the
# only names accepted are plain identifiers, which is what keeps that
# interpolation from being an injection hole. See ADR-0006.
_IDENTIFIER = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")

# The schema of one version row. ``version`` is the primary key, so the number
# the database hands out is unique by construction; ``bundle_json`` is the whole
# configuration of that version, stored as it was written and never rewritten,
# which is what makes diff and rollback a read instead of a computation. The DDL
# is idempotent, so a restart can call it again. See ADR-0006.
_CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS {table} ("
    "version INTEGER PRIMARY KEY, "
    "bundle_json TEXT NOT NULL, "
    "created_at DOUBLE PRECISION NOT NULL, "
    "change_id TEXT)"
)

# The append: the number comes out of the rows that are already there, in the
# same statement that writes the new one, so nothing in the application has to
# remember the head. See ADR-0006.
_APPEND = (
    "INSERT INTO {table} (version, bundle_json, created_at, change_id) "
    "SELECT COALESCE(MAX(version), 0) + 1, %s, %s, %s FROM {table} "
    "RETURNING version, created_at, change_id"
)

_SELECT = "SELECT version, bundle_json, created_at, change_id FROM {table}"


class _Cursor(Protocol):
    """The cursor this repository needs, and no more. Duck-typed: any DB-API cursor fits."""

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> Any:
        """Run one statement.

        Args:
            sql: The statement, with ``%s`` placeholders.
            params: The values bound to those placeholders.

        Returns:
            Whatever the driver returns; this repository ignores it.
        """
        ...

    def fetchone(self) -> tuple[Any, ...] | None:
        """Read one row.

        Returns:
            The next row, or ``None`` when the statement returned none.
        """
        ...

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Read every row left.

        Returns:
            The rows, in the order the server returned them.
        """
        ...


class _Connection(Protocol):
    """The connection this repository needs, and no more. Duck-typed: any DB-API connection fits."""

    def cursor(self) -> _Cursor:
        """Open a cursor on this connection.

        Returns:
            A cursor bound to this connection.
        """
        ...

    def commit(self) -> None:
        """Commit the transaction opened since the last commit or rollback."""
        ...


class PostgresVersionStore:
    """The configuration version repository, backed by PostgreSQL. See ADR-0006.

    **This repository is immutable**: it appends version rows and reads them
    back, and it never issues an ``UPDATE`` or a ``DELETE`` against a row it has
    written. An old row therefore stays exactly as it was written, which is what
    makes a rollback a read of the previous row instead of a rewrite of the
    current one. See ADR-0006.

    The connection is injected and owned by the caller: this object neither opens
    nor closes it, and it commits only what it wrote. No clock is read here and
    no socket is opened here — time arrives as the ``now`` argument of
    ``append``, and the only I/O is the SQL against the injected connection
    (AGENT.md §5). ADR-0007 is why the governance data lives here rather than in
    Redis: it is the record an audit reads.

    Attributes:
        table: The table holding the version rows.
    """

    def __init__(self, connection: _Connection, table: str = DEFAULT_TABLE) -> None:
        """Wrap an open connection as a version repository. Nothing is read or written yet.

        No clock is read and no statement is sent here: the caller owns the
        connection, and the schema is created by ``ensure_schema`` when the
        caller asks for it (AGENT.md §5).

        Args:
            connection: An open DB-API connection: this repository asks it for
                cursors and commits through it.
            table: The table holding the version rows. Tests and parallel
                deployments pass their own so they cannot collide.

        Raises:
            ValueError: If ``table`` is not a bare SQL identifier: it cannot be
                a bound parameter, so it is interpolated, and only a bare
                identifier is safe to interpolate.
        """
        if not _IDENTIFIER.match(table):
            raise ValueError(f"table must be a bare SQL identifier, got {table!r}")
        self._connection = connection
        self.table = table

    @classmethod
    def from_dsn(cls, dsn: str, table: str = DEFAULT_TABLE) -> PostgresVersionStore:
        """Build a repository by connecting to ``dsn``. This is the production entry point.

        The driver is imported here, not at module scope, so this module stays
        importable — and unit-testable — on a host without ``psycopg`` installed.
        See ADR-0007.

        Args:
            dsn: The PostgreSQL connection string.
            table: The table holding the version rows.

        Returns:
            A repository on a connection this call opened.
        """
        # Imported here on purpose: the driver must stay optional, so this module
        # is importable on a host without psycopg. See ADR-0007.
        import psycopg

        return cls(psycopg.connect(dsn), table=table)

    def ensure_schema(self) -> None:
        """Create the version table if it does not exist. Idempotent: a restart may call it again.

        The row shape is the schema ADR-0006 fixes: a number, the configuration
        as written, the time the caller says it was written, and the change order
        that produced it. See ADR-0006.
        """
        cursor = self._connection.cursor()
        cursor.execute(_CREATE_TABLE.format(table=self.table))
        self._connection.commit()

    def append(
        self,
        bundle: ConfigBundle,
        now: float,
        change_id: str | None = None,
    ) -> ConfigVersion:
        """Append a version, leaving every row already written untouched. See ADR-0006.

        The number is derived and written in one statement, out of the rows that
        are already in the table, so it is the database's answer and not a
        counter this process kept: a restart, or a second process appending at
        the same time, cannot produce two rows with the same number. The row is
        committed before this returns, and it is never updated afterwards.

        Args:
            bundle: The configuration to store as the new version.
            now: When the row is written, injected by the caller; this module
                reads no clock (AGENT.md §5).
            change_id: The change order that produced this version. ``None``
                only for a version written outside a change order, which
                ADR-0006 forbids in production. REQ-NF-10.

        Returns:
            The appended version, numbered one higher than the previous head, or
            1 when the table was empty.
        """
        cursor = self._connection.cursor()
        cursor.execute(
            _APPEND.format(table=self.table),
            (_encode(bundle), now, change_id),
        )
        row = cursor.fetchone()
        self._connection.commit()
        if row is None:
            raise RuntimeError(f"appending to {self.table} returned no row")
        version, created_at, stored_change_id = row
        return ConfigVersion(
            version=int(version),
            bundle=bundle,
            created_at=float(created_at),
            change_id=None if stored_change_id is None else str(stored_change_id),
        )

    def latest(self) -> ConfigVersion | None:
        """The newest version.

        Returns:
            The last appended version, or ``None`` when nothing was appended.
        """
        return self._read_one(f"{_SELECT.format(table=self.table)} ORDER BY version DESC LIMIT 1")

    def get(self, version: int) -> ConfigVersion | None:
        """Read one version out of history.

        Args:
            version: The version number to read.

        Returns:
            The version, or ``None`` when it was never written.
        """
        return self._read_one(f"{_SELECT.format(table=self.table)} WHERE version = %s", (version,))

    def history(self) -> tuple[ConfigVersion, ...]:
        """The whole history, oldest first.

        Returns:
            Every version ever appended, in append order.
        """
        cursor = self._connection.cursor()
        cursor.execute(f"{_SELECT.format(table=self.table)} ORDER BY version ASC")
        return tuple(_decode(row) for row in cursor.fetchall())

    def _read_one(self, sql: str, params: tuple[object, ...] = ()) -> ConfigVersion | None:
        """Read at most one version row.

        Args:
            sql: The statement to run.
            params: The values bound to its placeholders.

        Returns:
            The version, or ``None`` when the statement matched no row.
        """
        cursor = self._connection.cursor()
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        return _decode(row)


def _encode(bundle: ConfigBundle) -> str:
    """Render a configuration version as the JSON text of one row.

    The bundle and the rules and switches inside it are plain dataclasses, so
    ``asdict`` renders them without a hand-written mapping that would have to be
    kept in step with the contract. Tuples become JSON arrays, and ``_decode``
    turns them back into tuples, which is what the contract declares. See
    ADR-0006.

    Args:
        bundle: The configuration version to render.

    Returns:
        The JSON text stored in ``bundle_json``.
    """
    return json.dumps(dataclasses.asdict(bundle), sort_keys=True)


def _decode(row: tuple[Any, ...]) -> ConfigVersion:
    """Rebuild a version row read out of PostgreSQL.

    Args:
        row: One row, as ``version, bundle_json, created_at, change_id``.

    Returns:
        The version, with its configuration rebuilt as dataclasses.
    """
    version, bundle_json, created_at, change_id = row
    bundled = json.loads(bundle_json)
    return ConfigVersion(
        version=int(version),
        bundle=ConfigBundle(
            version=bundled["version"],
            rules=tuple(RuleDTO(**rule) for rule in bundled["rules"]),
            # A bundle written before a switch existed has no ``toggles`` key;
            # reading it back as no switches is the fail-closed answer. ADR-0020.
            toggles=tuple(ToggleDTO(**toggle) for toggle in bundled.get("toggles", ())),
        ),
        created_at=float(created_at),
        change_id=None if change_id is None else str(change_id),
    )
