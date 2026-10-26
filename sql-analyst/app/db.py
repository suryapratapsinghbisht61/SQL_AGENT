"""Database engine, schema introspection and guarded query execution."""
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import Connection

from app.config import settings


@lru_cache
def get_engine() -> Engine:
    """Engine for the read-only role in DATABASE_URL."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_schema_text() -> str:
    """Compact schema description: one line per table, plus its foreign keys."""
    insp = inspect(get_engine())
    lines = []
    for table in sorted(insp.get_table_names()):
        pk = set(insp.get_pk_constraint(table)["constrained_columns"])
        cols = ", ".join(
            f"{c['name']} {c['type']}{' PK' if c['name'] in pk else ''}" for c in insp.get_columns(table)
        )
        lines.append(f"{table}({cols})")
        for fk in insp.get_foreign_keys(table):
            lines.append(
                f"  FK {table}({', '.join(fk['constrained_columns'])})"
                f" -> {fk['referred_table']}({', '.join(fk['referred_columns'])})"
            )
    return "\n".join(lines)


def _guard(conn: Connection) -> None:
    # Belt and braces on top of the read-only role: read-only txn + per-statement timeout.
    conn.execute(text("SET TRANSACTION READ ONLY"))
    conn.execute(text(f"SET LOCAL statement_timeout = {int(settings.statement_timeout_seconds * 1000)}"))


def explain(sql: str) -> None:
    """Run EXPLAIN (no execution); raises a SQLAlchemy error if the query is invalid."""
    with get_engine().begin() as conn:
        _guard(conn)
        conn.execute(text("EXPLAIN " + sql))


def run_query(sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    """Execute a SELECT and return (columns, rows), at most ROW_LIMIT rows."""
    with get_engine().begin() as conn:
        _guard(conn)
        # Server-side cursor so Postgres stops producing rows after the limit.
        result = conn.execution_options(stream_results=True).execute(text(sql))
        columns = list(result.keys())
        rows = [dict(r._mapping) for r in result.fetchmany(settings.row_limit)]
        result.close()
    return columns, rows
