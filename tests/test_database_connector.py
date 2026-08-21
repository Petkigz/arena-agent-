"""DatabaseConnector tests — read-only SQL against SQLite (real) plus graceful
degradation for Postgres/MySQL (optional drivers, no server in sandbox)."""

import importlib.util
import sqlite3

from app.tools.database_connector import DatabaseConnector

HAS_PSYCOPG = importlib.util.find_spec("psycopg2") is not None
HAS_PYMYSQL = importlib.util.find_spec("pymysql") is not None


def _make_sqlite(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE sales (region TEXT, amount INTEGER)")
    conn.execute("INSERT INTO sales VALUES ('west', 10), ('east', 20), ('west', 30)")
    conn.commit()
    conn.close()
    return str(db)


def test_query_sqlite(tmp_path):
    db = _make_sqlite(tmp_path)
    res = DatabaseConnector.query("sqlite", "SELECT region, SUM(amount) AS total FROM sales GROUP BY region", database=db)
    assert res["success"] is True
    assert res["count"] == 2


def test_query_returns_dict_rows(tmp_path):
    db = _make_sqlite(tmp_path)
    res = DatabaseConnector.query("sqlite", "SELECT * FROM sales", database=db)
    assert res["success"] is True
    assert res["rows"][0]["region"] in ("west", "east")


def test_query_rejects_write(tmp_path):
    db = _make_sqlite(tmp_path)
    assert DatabaseConnector.query("sqlite", "DELETE FROM sales", database=db)["success"] is False
    assert DatabaseConnector.query("sqlite", "DROP TABLE sales", database=db)["success"] is False
    assert DatabaseConnector.query("sqlite", "INSERT INTO sales VALUES ('x', 1)", database=db)["success"] is False


def test_query_requires_sql(tmp_path):
    db = _make_sqlite(tmp_path)
    assert DatabaseConnector.query("sqlite", "  ", database=db)["success"] is False


def test_unsupported_engine():
    res = DatabaseConnector.query("oracle", "SELECT 1")
    assert res["success"] is False
    assert "Unsupported engine" in res["error"]


def test_sqlite_requires_path():
    assert DatabaseConnector.query("sqlite", "SELECT 1")["success"] is False


def test_sqlite_missing_db_degrades():
    res = DatabaseConnector.query("sqlite", "SELECT 1", database="/nonexistent/nowhere.db")
    assert res["success"] is False
    assert "Could not connect" in res["error"]


def test_list_tables_sqlite(tmp_path):
    db = _make_sqlite(tmp_path)
    res = DatabaseConnector.list_tables("sqlite", database=db)
    assert res["success"] is True
    assert "sales" in res["tables"]


def test_list_tables_unsupported_engine():
    assert DatabaseConnector.list_tables("oracle")["success"] is False


def test_postgres_missing_driver():
    if HAS_PSYCOPG:
        import pytest
        pytest.skip("psycopg2 installed — skipping missing-driver path")
    res = DatabaseConnector.query("postgres", "SELECT 1", host="127.0.0.1")
    assert res["success"] is False
    assert "psycopg2" in res["error"]


def test_mysql_missing_driver():
    if HAS_PYMYSQL:
        import pytest
        pytest.skip("pymysql installed — skipping missing-driver path")
    res = DatabaseConnector.query("mysql", "SELECT 1", host="127.0.0.1")
    assert res["success"] is False
    assert "pymysql" in res["error"]
