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

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")  # single-quoted values, '' escape
_QUOTED_IDENT = re.compile(r'"(?:[^"]|"")*"')  # double-quoted identifiers
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def ensure_read_only(sql: str) -> str:
    """Validate that ``sql`` is a single read-only statement; return it cleaned.

    Steps:
      1. strip comments — so a keyword cannot hide behind ``--`` or ``/* */``;
      2. blank out string/identifier literals before scanning — so the word
         ``delete`` inside a value is not mistaken for a DELETE statement, and a
         ``;`` inside a string is not treated as a statement separator;
      3. require exactly one statement;
      4. require it to begin with SELECT or WITH;
      5. reject any forbidden statement keyword anywhere in the query.

    Raises:
        SqlGuardError: on any violation (a deliberate refusal, not a failure).

    Returns:
        The comment-stripped, single statement (trailing ``;`` removed).
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
