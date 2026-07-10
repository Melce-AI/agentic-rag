#!/bin/sh
# Create the read-WRITE role the Sentinel MCP `sql_execute` tool connects with.
#
# This is the write half of the two-tier SQL design. Unlike sentinel_ro (which
# physically cannot write — see 03_create_readonly_role.sh), this role MAY run
# UPDATE/DELETE. Two things keep it safe:
#   1. It is granted DML on the operational tables ONLY (never `products`, never
#      the whole schema); INSERT/TRUNCATE/DDL are never granted.
#   2. Every statement is gated by human approval (HITL interrupt) in the agent
#      graph before it ever executes.
#
# Keep the table list in sync with settings.postgres_writable_tables and the
# ensure_write_safe() guard (src/mcp_server/guards.py).
#
# Runs once during first-time DB init. Password comes from the container env so
# no credential is hardcoded in a committed file.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sentinel_rw') THEN
            CREATE ROLE sentinel_rw LOGIN PASSWORD '${SENTINEL_RW_PASSWORD}';
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO sentinel_rw;
    GRANT USAGE ON SCHEMA public TO sentinel_rw;

    -- Write tier: SELECT (needed for WHERE / RETURNING) + UPDATE + DELETE, on
    -- the operational tables ONLY. No INSERT, no TRUNCATE, no DDL, and nothing
    -- on `products` or any other table.
    GRANT SELECT, UPDATE, DELETE ON orders, customers, order_items TO sentinel_rw;

    -- Belt and suspenders: make sure destructive/DDL-adjacent privileges never
    -- leak in on any table in the schema.
    REVOKE INSERT, TRUNCATE ON ALL TABLES IN SCHEMA public FROM sentinel_rw;
EOSQL
