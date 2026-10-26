"""SQL safety checks: a single read-only SELECT, no dangerous functions, and it must EXPLAIN."""
import sqlglot
from sqlalchemy.exc import DBAPIError
from sqlglot import exp

from app import db

FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Drop, exp.Alter, exp.TruncateTable,
    exp.Create, exp.Grant, exp.Copy, exp.Command, exp.Into, exp.Lock,
)
DANGEROUS_PREFIXES = ("pg_", "lo_", "dblink")
DANGEROUS_FUNCS = {"set_config", "query_to_xml", "query_to_xml_and_xmlschema", "table_to_xml", "current_setting"}


def check_static(sql: str) -> str | None:
    """Parse-level checks. Returns an error message, or None if the SQL is acceptable."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        return f"SQL syntax error: {str(e).splitlines()[0]}"
    if len(statements) != 1:
        return f"Expected exactly one statement, got {len(statements)}."
    stmt = statements[0]
    if not isinstance(stmt, (exp.Select, exp.SetOperation)):
        return f"Only SELECT queries are allowed, got {stmt.key.upper()}."
    for node in stmt.walk():
        if isinstance(node, FORBIDDEN_NODES):
            return f"Forbidden operation in query: {node.key.upper()}. Only plain SELECT is allowed."
        if isinstance(node, exp.Func):
            name = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if name.startswith(DANGEROUS_PREFIXES) or name in DANGEROUS_FUNCS:
                return f"Function {name}() is not allowed."
    return None


def validate_sql(sql: str) -> str | None:
    """Full validation: static checks, then EXPLAIN against the database."""
    if error := check_static(sql):
        return error
    try:
        db.explain(sql)
    except DBAPIError as e:
        return f"Database rejected the query: {str(e.orig).strip().splitlines()[0]}"
    return None
