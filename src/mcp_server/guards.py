"""Read-only SQL guard for the Sentinel MCP `sql_query` tool.

This is the SECOND, application-side layer of a defense-in-depth design. The
FIRST layer is the database itself: the tool connects with the least-privilege
``sentinel_ro`` role that physically cannot write (see
``infra/postgres/initdb/03_create_readonly_role.sh``). This guard adds an
independent check so a write statement is refused *before* it ever reaches the
database — and with a clear, model-readable reason.

The guard is intentionally dependency-free and pure so it is trivial to unit
test exhaustively.
"""

import re
from collections.abc import Collection

from src.core.exceptions import SqlGuardError

# Statement keywords that must never run through a read-only tool. Matched as
# whole words after comments and string/identifier literals are removed, so a
# data-modifying CTE (``WITH x AS (DELETE ...)``) is caught too.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "insert",
        "update",
        "delete",
        "truncate",
        "drop",
        "alter",
        "create",
        "grant",
        "revoke",
        "merge",
        "call",
        "do",
        "copy",
        "vacuum",
        "analyze",
        "reindex",
        "cluster",
        "comment",
        "lock",
        "set",
        "reset",
        "begin",
        "commit",
        "rollback",
        "savepoint",
        "prepare",
        "execute",
        "explain",
    }
)

# A read query must start with one of these.
_ALLOWED_LEADING = ("select", "with")

# A write query must start with one of these — no WITH, so a data-modifying CTE
# cannot lead a write statement.
_WRITE_ALLOWED_LEADING = ("update", "delete")

# Statement-type keywords that must never appear in a write query. UPDATE/DELETE
# syntax words (SET, FROM, WHERE, USING, RETURNING) and SELECT (legal inside a
# subquery) are deliberately absent so they don't false-positive.
_WRITE_FORBIDDEN = frozenset(
    {
        "insert",
        "truncate",
        "drop",
        "alter",
        "create",
        "grant",
        "revoke",
        "merge",
        "call",
        "do",
        "copy",
        "vacuum",
        "reindex",
        "cluster",
        "comment",
        "lock",
        "prepare",
        "execute",
        "savepoint",
        "begin",
        "commit",
        "rollback",
    }
)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")  # single-quoted values, '' escape
_QUOTED_IDENT = re.compile(r'"(?:[^"]|"")*"')  # double-quoted identifiers
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _clean_and_tokenize(sql: str) -> tuple[str, list[str]]:
    """Strip comments, enforce a single statement, and tokenize.

    Shared by ensure_read_only and ensure_write_safe: both need the same
    comment/literal-safe view before applying their own (opposite) whitelist.

    Steps:
      1. strip comments — so a keyword cannot hide behind ``--`` or ``/* */``;
      2. blank out string/identifier literals before scanning — so a keyword
         inside a value is not read as a statement, and a ``;`` inside a string
         is not treated as a statement separator;
      3. require exactly one statement.

    Raises:
        SqlGuardError: on empty input or more than one statement.

    Returns:
        ``(body, tokens)`` — the cleaned single statement (trailing ``;``
        removed, literals intact) and its lowercased word tokens scanned with
        literals removed.
    """
    if not sql or not sql.strip():
        raise SqlGuardError("query must not be empty")

    without_comments = _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql)).strip()
    if not without_comments:
        raise SqlGuardError("query has no executable statement")

    body = without_comments.rstrip(";").strip()

    # Scan with literals removed so a ';' inside a string is not a break.
    literal_free = _QUOTED_IDENT.sub(" ", _STRING_LITERAL.sub(" ", body))
    if ";" in literal_free:
        raise SqlGuardError("only a single SQL statement is allowed")

    tokens = [word.lower() for word in _WORD.findall(literal_free)]
    if not tokens:
        raise SqlGuardError("query has no executable statement")

    return body, tokens


def ensure_read_only(sql: str) -> str:
    """Validate that ``sql`` is a single read-only statement; return it cleaned.

    On top of the shared cleaning (``_clean_and_tokenize``) it:
      - requires a SELECT/WITH leading keyword;
      - rejects any forbidden statement keyword anywhere — which also catches
        data-modifying CTEs like ``WITH x AS (DELETE ... RETURNING *) SELECT``.

    Raises:
        SqlGuardError: on any violation (a deliberate refusal, not a failure).

    Returns:
        The comment-stripped, single statement (trailing ``;`` removed).
    """
    body, tokens = _clean_and_tokenize(sql)

    if tokens[0] not in _ALLOWED_LEADING:
        raise SqlGuardError(
            f"only SELECT/WITH queries are allowed, got '{tokens[0].upper()}'"
        )

    forbidden = sorted({token for token in tokens if token in _FORBIDDEN_KEYWORDS})
    if forbidden:
        raise SqlGuardError(
            "query contains forbidden keyword(s): "
            + ", ".join(keyword.upper() for keyword in forbidden)
        )

    return body


def _target_table(verb: str, tokens: list[str]) -> str | None:
    """Best-effort extraction of the mutated table from a write statement.

    ``UPDATE [ONLY] <table> SET ...``  |  ``DELETE FROM [ONLY] <table> ...``.
    Tables must be referenced unqualified (matching the sample schema); a
    schema-qualified name won't match the writable set and is refused upstream.
    """
    if verb == "update":
        rest = tokens[1:]
    else:  # delete
        if len(tokens) < 2 or tokens[1] != "from":
            return None
        rest = tokens[2:]
    if rest and rest[0] == "only":
        rest = rest[1:]
    return rest[0] if rest else None


def ensure_write_safe(sql: str, writable_tables: Collection[str]) -> str:
    """Validate a single, WHERE-qualified UPDATE/DELETE on an allowed table.

    The write-tier mirror of ensure_read_only. On top of the shared cleaning it:
      1. requires a leading UPDATE or DELETE (no WITH — data-modifying CTEs are
         refused outright);
      2. rejects any other statement-type keyword (INSERT/TRUNCATE/DDL/...);
      3. requires a WHERE clause — an unqualified UPDATE/DELETE that would touch
         every row is refused *before* it ever reaches human approval;
      4. requires the target table to be one of ``writable_tables``.

    Raises:
        SqlGuardError: on any violation (a deliberate refusal, not a failure).

    Returns:
        The comment-stripped, single statement (trailing ``;`` removed).
    """
    body, tokens = _clean_and_tokenize(sql)

    verb = tokens[0]
    if verb not in _WRITE_ALLOWED_LEADING:
        raise SqlGuardError(
            f"only UPDATE/DELETE statements are allowed here, got '{verb.upper()}'"
        )

    forbidden = sorted({token for token in tokens if token in _WRITE_FORBIDDEN})
    if forbidden:
        raise SqlGuardError(
            "query contains forbidden keyword(s): "
            + ", ".join(keyword.upper() for keyword in forbidden)
        )

    if "where" not in tokens:
        raise SqlGuardError(
            "a WHERE clause is required — an unqualified UPDATE/DELETE that "
            "would affect every row is refused"
        )

    allowed = {name.lower() for name in writable_tables}
    table = _target_table(verb, tokens)
    if table is None or table not in allowed:
        raise SqlGuardError(
            f"table '{table or '?'}' is not writable; allowed: "
            + ", ".join(sorted(allowed))
        )

    return body
