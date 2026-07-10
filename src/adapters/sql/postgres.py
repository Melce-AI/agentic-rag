"""Async Postgres adapter for the Sentinel MCP SQL tools.

External-system adapter (like ``QdrantManager``): MCP tools and services never
talk to psycopg directly, they go through this. One instance per DB role:

- ``postgres_manager`` — the least-privilege ``sentinel_ro`` role; every query
  runs inside a read-only transaction (the ``sql_query`` tool + schema discovery).
- ``postgres_write_manager`` — the ``sentinel_rw`` role; ``run_write`` commits an
  UPDATE/DELETE (the HITL-gated ``sql_execute`` tool).

The pool/connection machinery is shared; only the role and the transaction mode
differ. These are the infrastructure half of the project's defense-in-depth
design; the SQL guards (``src/mcp_server/guards.py``) are the independent
application half.
"""

import logging
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.core.config import get_settings
from src.core.exceptions import SqlStoreInitializationError, SqlStoreOperationError
from src.observability.tracing import traced

logger = logging.getLogger(__name__)


class PostgresManager:
    """Manages a lazily-opened async connection pool for one Postgres role.

    Construct one per role (see the ``postgres_manager`` / ``postgres_write_manager``
    singletons below). The role + transaction mode is all that differs between a
    read-only and a write manager.
    """

    def __init__(self, user: str, password: str, row_limit: int) -> None:
        settings = get_settings()
        self._row_limit = max(1, row_limit)
        self._conninfo = (
            f"host={settings.postgres_host} "
            f"port={settings.postgres_port} "
            f"dbname={settings.postgres_db} "
            f"user={user} "
            f"password={password}"
        )
        self._pool: AsyncConnectionPool | None = None

    async def _get_pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            try:
                pool = AsyncConnectionPool(
                    self._conninfo, open=False, min_size=1, max_size=4
                )
                await pool.open(wait=True)
                self._pool = pool
                logger.info("Postgres read-only pool opened.")
            except Exception as exc:
                raise SqlStoreInitializationError(details={"error": str(exc)}) from exc
        return self._pool

    @traced("postgres.run_select")
    async def run_select(
        self, sql: str, params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Run a read-only query and return up to ``row_limit`` rows as dicts.

        The transaction is forced read-only as a third safety layer; rows are
        capped with ``fetchmany`` so a broad query can never stream an unbounded
        result set back through the tool.
        """
        pool = await self._get_pool()
        try:
            async with pool.connection() as conn:
                await conn.set_read_only(True)
                async with conn.cursor(row_factory=dict_row) as cursor:
                    await cursor.execute(sql, params)
                    rows = await cursor.fetchmany(self._row_limit)
            return [dict(row) for row in rows]
        except Exception as exc:
            raise SqlStoreOperationError(
                operation="run_select", details={"error": str(exc)}
            ) from exc

    @traced("postgres.run_write")
    async def run_write(self, sql: str, params: tuple[Any, ...] | None = None) -> int:
        """Execute one write statement, commit, and return the affected row count.

        Runs in a read-WRITE transaction that commits on success. Only the write
        manager (``sentinel_rw`` role) can actually mutate — calling this through
        the read-only role fails at the database, by design (defense in depth).
        The statement must already have passed ``ensure_write_safe`` upstream;
        this adapter does not re-validate SQL.
        """
        pool = await self._get_pool()
        try:
            async with pool.connection() as conn:
                # Symmetric with run_select's read-only flag: make this session
                # explicitly writable before the transaction begins.
                await conn.set_read_only(False)
                async with conn.cursor() as cursor:
                    await cursor.execute(sql, params)
                    rowcount = cursor.rowcount
                await conn.commit()
            return rowcount
        except Exception as exc:
            raise SqlStoreOperationError(
                operation="run_write", details={"error": str(exc)}
            ) from exc

    async def list_tables(self) -> list[str]:
        """Return the public-schema table names (for schema discovery)."""
        rows = await self.run_select(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        return [row["table_name"] for row in rows]

    async def describe_table(self, table_name: str) -> list[dict[str, Any]]:
        """Return column name, type, and nullability for one public-schema table."""
        return await self.run_select(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s "
            "ORDER BY ordinal_position",
            (table_name,),
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


# Singletons, mirroring qdrant_manager. Each pool opens lazily on first use.
_settings = get_settings()

# Read-only (sentinel_ro) — the sql_query tool and schema discovery.
postgres_manager = PostgresManager(
    user=_settings.postgres_ro_user,
    password=_settings.postgres_ro_password.get_secret_value(),
    row_limit=_settings.postgres_query_row_limit,
)

# Write-capable (sentinel_rw) — the HITL-gated sql_execute tool. Same machinery,
# write role, committing transactions.
postgres_write_manager = PostgresManager(
    user=_settings.postgres_rw_user,
    password=_settings.postgres_rw_password.get_secret_value(),
    row_limit=_settings.postgres_query_row_limit,
)
