import pytest

from app.validator import check_static, validate_sql


@pytest.mark.parametrize("sql", [
    "SELECT name FROM artist LIMIT 5",
    "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
    "SELECT 1 UNION SELECT 2",
])
def test_valid_select_passes_static(sql):
    assert check_static(sql) is None


@pytest.mark.parametrize("sql, fragment", [
    ("SELECT 1; DROP TABLE x", "exactly one statement"),
    ("INSERT INTO artist (name) VALUES ('x')", "Only SELECT"),
    ("UPDATE artist SET name = 'x'", "Only SELECT"),
    ("DELETE FROM artist", "Only SELECT"),
    ("DROP TABLE artist", "Only SELECT"),
    ("TRUNCATE artist", "Only SELECT"),
    ("GRANT SELECT ON artist TO public", "Only SELECT"),
    ("COPY artist TO STDOUT", "Only SELECT"),
    ("WITH d AS (DELETE FROM artist RETURNING *) SELECT * FROM d", "Forbidden"),
    ("SELECT * INTO new_t FROM artist", "Forbidden"),
    ("SELECT pg_sleep(10)", "pg_sleep"),
    ("SELECT pg_catalog.pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT lo_import('/etc/passwd')", "lo_import"),
    ("SELECT * FROM dblink('host=x', 'select 1') AS t(a int)", "dblink"),
    ("", "exactly one statement"),
])
def test_rejected(sql, fragment):
    error = check_static(sql)
    assert error and fragment in error


def test_valid_select_passes_explain(live_db):
    assert validate_sql("SELECT name FROM artist ORDER BY name LIMIT 3") is None


def test_nonexistent_table_caught(live_db):
    error = validate_sql("SELECT * FROM no_such_table")
    assert error and "no_such_table" in error


def test_nonexistent_column_caught(live_db):
    error = validate_sql("SELECT nope FROM artist")
    assert error and "nope" in error
