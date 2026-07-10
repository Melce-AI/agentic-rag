"""Tests for the write-tier SQL guard (ensure_write_safe).

The mirror of test_sql_guard.py for the write path. Pure and dependency-free:
no DB, no config — the writable-table set is passed in explicitly. It exercises
the guard exhaustively (allows a WHERE-qualified UPDATE/DELETE on an allowed
table; rejects everything else).
"""

import pytest

from src.core.exceptions import SqlGuardError
from src.mcp_server.guards import ensure_write_safe

WRITABLE = frozenset({"orders", "customers", "order_items"})


def _ok(sql: str) -> str:
    return ensure_write_safe(sql, WRITABLE)


# --- allowed: single, WHERE-qualified UPDATE/DELETE on a writable table ---


def test_allows_update_with_where():
    body = _ok("UPDATE orders SET status = 'cancelled' WHERE order_id = 8")
    assert body.startswith("UPDATE orders")


def test_allows_delete_with_where():
    assert _ok("DELETE FROM customers WHERE customer_id = 4") == (
        "DELETE FROM customers WHERE customer_id = 4"
    )


def test_strips_trailing_semicolon():
    assert _ok("DELETE FROM orders WHERE order_id = 1;").endswith("order_id = 1")


def test_allows_update_only_keyword():
    _ok("UPDATE ONLY orders SET status = 'x' WHERE order_id = 1")


# --- refused ---


def test_rejects_update_without_where():
    with pytest.raises(SqlGuardError, match="WHERE"):
        _ok("UPDATE orders SET status = 'cancelled'")


def test_rejects_delete_without_where():
    with pytest.raises(SqlGuardError, match="WHERE"):
        _ok("DELETE FROM orders")


def test_rejects_non_writable_table():
    with pytest.raises(SqlGuardError, match="not writable"):
        _ok("UPDATE products SET unit_price = 0 WHERE product_id = 1")


def test_rejects_select():
    with pytest.raises(SqlGuardError, match="UPDATE/DELETE"):
        _ok("SELECT * FROM orders WHERE order_id = 1")


def test_rejects_leading_with_cte():
    with pytest.raises(SqlGuardError, match="UPDATE/DELETE"):
        _ok("WITH x AS (SELECT 1) UPDATE orders SET status='x' WHERE order_id=1")


def test_rejects_multiple_statements():
    with pytest.raises(SqlGuardError, match="single SQL statement"):
        _ok("UPDATE orders SET status='x' WHERE order_id=1; DROP TABLE orders")


def test_rejects_truncate():
    with pytest.raises(SqlGuardError, match="UPDATE/DELETE"):
        _ok("TRUNCATE orders")


def test_rejects_empty():
    with pytest.raises(SqlGuardError, match="empty"):
        _ok("   ")


def test_where_only_inside_a_string_does_not_satisfy_where_clause():
    # 'where' hidden in a string literal must NOT satisfy the WHERE requirement.
    with pytest.raises(SqlGuardError, match="WHERE"):
        _ok("UPDATE orders SET status = 'where'")
