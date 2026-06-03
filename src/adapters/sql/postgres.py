"""Read-only async Postgres adapter for the Sentinel MCP SQL tool.

External-system adapter (like ``QdrantManager``): MCP tools and services never
talk to psycopg directly, they go through this. It connects with the
least-privilege ``sentinel_ro`` role and runs every query inside a read-only
transaction — the infrastructure half of the project's defense-in-depth design.
The SQL guard (``src/mcp_server/guards.py``) is the independent application half.
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
    """Manages a lazily-opened async connection pool to the read-only role."""

    def __init__(self) -> None:
        settings = get_settings()
        self._row_limit = max(1, settings.postgres_query_row_limit)
        self._conninfo = (
            f"host={settings.postgres_host} "
            f"port={settings.postgres_port} "
            f"dbname={settings.postgres_db} "
            f"user={settings.postgres_ro_user} "
            f"password={settings.postgres_ro_password.get_secret_value()}"
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


# Singleton, mirroring qdrant_manager. The pool opens lazily on first use.
postgres_manager = PostgresManager()
