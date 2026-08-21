"""DatabaseConnector.execute tests — write path (Level 3) with foot-gun rails."""

import sqlite3

from app.tools.database_connector import DatabaseConnector


def _make_sqlite(tmp_path):
    db = tmp_path / "w.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()
    return str(db)


def _count(tmp_path, db):
    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    conn.close()
    return n


def test_execute_insert(tmp_path):
    db = _make_sqlite(tmp_path)
    res = DatabaseConnector.execute("sqlite", "INSERT INTO t (name) VALUES ('a')", database=db)
    assert res["success"] is True
    assert res["rowcount"] == 1
    assert _count(tmp_path, db) == 1


def test_execute_rolls_back_on_error(tmp_path):
    db = _make_sqlite(tmp_path)
    res = DatabaseConnector.execute("sqlite", "INSERT INTO nonexistent VALUES (1)", database=db)
    assert res["success"] is False
    assert _count(tmp_path, db) == 0  # nothing committed


def test_execute_read_returns_rows(tmp_path):
    db = _make_sqlite(tmp_path)
    DatabaseConnector.execute("sqlite", "INSERT INTO t (name) VALUES ('a'), ('b')", database=db)
    res = DatabaseConnector.execute("sqlite", "SELECT * FROM t", database=db)
    assert res["success"] is True
    assert res["count"] == 2


def test_unfiltered_delete_requires_flag(tmp_path):
    db = _make_sqlite(tmp_path)
    res = DatabaseConnector.execute("sqlite", "DELETE FROM t", database=db)
    assert res["success"] is False
    assert "allow_unfiltered" in res["error"]
    # With the flag, it proceeds.
    res = DatabaseConnector.execute("sqlite", "DELETE FROM t", database=db, allow_unfiltered=True)
    assert res["success"] is True


def test_unfiltered_update_requires_flag(tmp_path):
    db = _make_sqlite(tmp_path)
    res = DatabaseConnector.execute("sqlite", "UPDATE t SET name='x'", database=db)
    assert res["success"] is False
    assert "allow_unfiltered" in res["error"]


def test_where_clause_bypasses_guard(tmp_path):
    db = _make_sqlite(tmp_path)
    DatabaseConnector.execute("sqlite", "INSERT INTO t (name) VALUES ('a')", database=db)
    res = DatabaseConnector.execute("sqlite", "DELETE FROM t WHERE id = 1", database=db)
    assert res["success"] is True
    assert _count(tmp_path, db) == 0


def test_drop_database_requires_flag():
    res = DatabaseConnector.execute("sqlite", "DROP DATABASE x", database="/tmp/x.db")
    assert res["success"] is False
    assert "allow_destructive" in res["error"]


def test_execute_requires_sql(tmp_path):
    db = _make_sqlite(tmp_path)
    assert DatabaseConnector.execute("sqlite", "  ", database=db)["success"] is False


def test_guard_ignores_sql_comments():
    # A commented-out DROP should not trip the destructive guard.
    assert DatabaseConnector._write_guard("SELECT 1 -- DROP DATABASE x", False, False) is None
    assert DatabaseConnector._write_guard("/* DROP DATABASE x */ SELECT 1", False, False) is None
