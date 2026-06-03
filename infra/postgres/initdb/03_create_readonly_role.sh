#!/bin/sh
# Create the read-only role the Sentinel MCP SQL tool connects with.
#
# This is the FIRST line of defense: even if the tool's SQL guard were bypassed,
# this database role physically cannot INSERT/UPDATE/DELETE. The guard in the
# application is the second, independent layer (defense in depth).
#
# Runs once during first-time DB init. Password comes from the container env so
# no credential is hardcoded in a committed file.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sentinel_ro') THEN
            CREATE ROLE sentinel_ro LOGIN PASSWORD '${SENTINEL_RO_PASSWORD}';
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO sentinel_ro;
    GRANT USAGE ON SCHEMA public TO sentinel_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO sentinel_ro;

    -- Future tables in this schema are readable too, without re-granting.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sentinel_ro;

    -- Belt and suspenders: make sure no write privilege ever leaks in.
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM sentinel_ro;
EOSQL
