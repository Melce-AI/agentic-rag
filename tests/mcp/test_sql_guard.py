"""Unit tests for the read-only SQL guard (defense-in-depth, layer 2)."""

import pytest

from src.core.exceptions import SqlGuardError
from src.mcp_server.guards import ensure_read_only


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select * from products",
        "  SELECT name FROM products WHERE category = 'Electronics'  ",
        "SELECT count(*) FROM orders;",  # trailing semicolon allowed
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
        "SELECT * FROM products -- a trailing comment\n",
        "SELECT 'delete me' AS label",  # forbidden word only inside a string
        "SELECT * FROM products WHERE name = 'a; b'",  # semicolon inside a string
    ],
)
def test_allows_read_only_queries(sql):
    # Should not raise; returns the cleaned statement without a trailing ';'.
    result = ensure_read_only(sql)
    assert not result.rstrip().endswith(";")
    assert result.strip()


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO products (name) VALUES ('x')",
        "UPDATE products SET unit_price = 0",
        "DELETE FROM orders",
        "DROP TABLE customers",
        "TRUNCATE orders",
        "ALTER TABLE products ADD COLUMN x int",
        "GRANT SELECT ON products TO public",
        "CREATE TABLE evil (id int)",
        "SET default_transaction_read_only = off",
        # Data-modifying CTE: leading WITH is allowed, but DELETE inside is caught.
        "WITH gone AS (DELETE FROM orders RETURNING *) SELECT * FROM gone",
        # Stacked statements: the second one must be blocked.
        "SELECT 1; DROP TABLE customers",
        # Keyword hidden behind a comment must still be caught.
        "SELECT 1; /* */ DELETE FROM orders",
    ],
)
def test_rejects_writes_and_multi_statements(sql):
    with pytest.raises(SqlGuardError):
        ensure_read_only(sql)


@pytest.mark.parametrize("sql", ["", "   ", "-- only a comment", "/* nothing */"])
def test_rejects_empty_or_commentonly(sql):
    with pytest.raises(SqlGuardError):
        ensure_read_only(sql)


def test_rejects_non_select_leading_keyword():
    with pytest.raises(SqlGuardError, match="SELECT/WITH"):
        ensure_read_only("EXPLAIN SELECT * FROM products")
