# Sentinel MCP — SQL Tool Design

How the LLM gets safe, read-only access to a relational database over MCP
(Vision Step 2). Reference: [../architecture.md](../architecture.md),
[../local_notes/VIZYON 1.md](../local_notes/VIZYON%201.md).

## Why MCP at all

The vision's interview line is the whole point: *"How does the model access the
database safely? — Through MCP, only with authorized tools."* The model never
holds a connection string or writes arbitrary SQL against prod. It can only call
the named tools the server exposes, and each tool is a controlled, audited
surface.

## The tools (discovery-first)

The SQL tools mirror the existing log tools' "discover, then act" shape so an
agent can orient itself before querying:

1. `list_tables()` — what tables exist.
2. `describe_table(name)` — a table's columns, types, nullability.
3. `sql_query(sql)` — run one read-only SELECT/WITH statement, rows as JSON.

Schema discovery matters: without it an LLM guesses column names and
hallucinates SQL. With it, queries are grounded in the real schema.

## Defense in depth — two independent layers

A single safeguard is one bug away from a write reaching prod. We use two
layers that fail independently:

1. **Database role (infrastructure).** The tool connects as `sentinel_ro`, a
   `LOGIN` role granted only `SELECT`. `INSERT/UPDATE/DELETE/TRUNCATE` are
   revoked. Even a perfect guard bypass cannot write — Postgres refuses.
   Defined in `infra/postgres/initdb/03_create_readonly_role.sh`.
2. **Application guard (`src/mcp_server/guards.py`).** `ensure_read_only()`
   refuses anything that is not a single SELECT/WITH *before* it reaches the DB,
   with a clear message the model can act on. It:
   - strips comments (a keyword can't hide behind `--` or `/* */`),
   - blanks string/identifier literals before scanning (so `'delete me'` is not
     read as DELETE, and a `;` inside a string is not a statement break),
   - requires exactly one statement,
   - requires a SELECT/WITH leading keyword,
   - rejects any forbidden statement keyword anywhere — which also catches
     data-modifying CTEs like `WITH x AS (DELETE ... RETURNING *) SELECT ...`.

A third, smaller belt: the adapter forces a read-only transaction and caps rows
with `fetchmany(row_limit)`, so a broad query can't stream an unbounded result.

> Future (Vision Step 3/4): destructive intent won't just be refused — it will
> trigger a LangGraph `interrupt()` for human approval (HITL). For now the
> read-only tool refuses outright.

## Layout & dependency direction

```
mcp_server/server.py   (tool definitions — thin)
  └─ guards.py         (pure, dependency-free SQL validation)
  └─ adapters/sql/postgres.py  (PostgresManager: pool, read-only, row cap)
        └─ core/config.py
```

The tool layer only wires guard + adapter together; it holds no SQL logic of its
own. `mcp_server` is an entrypoint (its own process), not a service other modules
import — agents will call it as a client.

## Sample data

Synthetic e-commerce schema (`customers`, `products`, `orders`, `order_items`)
seeded in `infra/postgres/initdb/`. Never load real or company data here
(AGENTS.md). It is rich enough for JOINs, `GROUP BY` aggregation (e.g. revenue
by product), and date filtering.

## Running it

```bash
# 1. Start Postgres (creates schema, seed, and the read-only role on first run)
docker compose -f infra/postgres/docker-compose.yml up -d

# 2a. Inspect the server interactively
uv run mcp dev src/mcp_server/server.py

# 2b. Or drive it like an agent would (stdio client, no Node required)
uv run python -m src.mcp_server.dev_client
```

When running the MCP server on the host (not in the Compose network), set
`POSTGRES_HOST=localhost` so it reaches the published port.

## Tests

- `tests/mcp/test_sql_guard.py` — the guard, exhaustively (allows reads; rejects
  writes, multi-statement, comment-hidden keywords, data-modifying CTEs).
- `tests/mcp/test_sql_tools.py` — the tools with the adapter mocked (no live DB):
  guard refusal short-circuits before any DB call; rows render as JSON.
