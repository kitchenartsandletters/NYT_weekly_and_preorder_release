import os
import sqlite3
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import types
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *a, **k: None))
psycopg2_module = types.ModuleType("psycopg2")
psycopg2_module.connect = lambda *a, **k: None
extras_mod = types.ModuleType("psycopg2.extras")
extras_mod.RealDictCursor = object
psycopg2_module.extras = extras_mod
sys.modules.setdefault("psycopg2", psycopg2_module)
sys.modules.setdefault("psycopg2.extras", extras_mod)

from refactor.src import anomalies
from refactor.utils import db as db_utils


@pytest.fixture()
def conn(monkeypatch):
    sqlite = sqlite3.connect(':memory:')
    sqlite.row_factory = sqlite3.Row
    sqlite.executescript(
        """
        CREATE TABLE preorders (
            isbn TEXT PRIMARY KEY,
            title TEXT,
            vendor TEXT,
            pub_date TEXT,
            tagged_preorder BOOLEAN DEFAULT 0,
            in_preorder_collection BOOLEAN DEFAULT 0
        );
        CREATE TABLE releases (
            isbn TEXT PRIMARY KEY
        );
        CREATE TABLE anomalies_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn VARCHAR(13) NOT NULL,
            reason TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(isbn, reason)
        );
        """
    )
    class CursorWrapper:
        def __init__(self, cur):
            self._cur = cur

        def execute(self, query, params=None):
            if params is not None:
                query = query.replace("%s", "?")
                return self._cur.execute(query, params)
            return self._cur.execute(query)

        def executemany(self, query, param_seq):
            query = query.replace("%s", "?")
            return self._cur.executemany(query, param_seq)

        def fetchone(self):
            return self._cur.fetchone()

        def fetchall(self):
            return self._cur.fetchall()

        def __getattr__(self, name):
            return getattr(self._cur, name)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

    class ConnWrapper:
        def __init__(self, c):
            self._c = c

        def cursor(self):
            return CursorWrapper(self._c.cursor())

        def __getattr__(self, name):
            return getattr(self._c, name)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                self._c.commit()
            else:
                self._c.rollback()

    wrapper = ConnWrapper(sqlite)
    monkeypatch.setattr(db_utils, "get_connection", lambda: wrapper)
    yield sqlite
    sqlite.close()


def fetch_anomalies(conn):
    return [dict(r) for r in conn.execute("SELECT isbn, reason FROM anomalies_log").fetchall()]


def test_no_anomaly_for_valid_product(conn):
    conn.execute(
        "INSERT INTO preorders (isbn, title, pub_date, tagged_preorder) VALUES (?, ?, ?, 1)",
        ("1234567890123", "Book", "2030-01-01"),
    )
    anomalies.log_anomalies()
    assert fetch_anomalies(conn) == []


def test_detect_missing_pub_date(conn):
    conn.execute(
        "INSERT INTO preorders (isbn, title, tagged_preorder) VALUES (?, ?, 1)",
        ("1111111111111", "Book"),
    )
    anomalies.log_anomalies()
    rows = fetch_anomalies(conn)
    assert rows == [{"isbn": "1111111111111", "reason": "Missing pub_date"}]


def test_detect_malformed_date(conn):
    conn.execute(
        "INSERT INTO preorders (isbn, title, pub_date, tagged_preorder) VALUES (?, ?, ?, 1)",
        ("2222222222222", "Book", "2025/13/99"),
    )
    anomalies.log_anomalies()
    rows = fetch_anomalies(conn)
    assert rows == [{"isbn": "2222222222222", "reason": "Malformed pub_date"}]


def test_detect_old_pub_date(conn):
    old_date = (date.today() - timedelta(days=40)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO preorders (isbn, title, pub_date, tagged_preorder) VALUES (?, ?, ?, 1)",
        ("3333333333333", "Book", old_date),
    )
    anomalies.log_anomalies()
    rows = fetch_anomalies(conn)
    assert rows == [{"isbn": "3333333333333", "reason": "pub_date older than 30 days"}]


def test_detect_invalid_isbn(conn):
    conn.execute(
        "INSERT INTO preorders (isbn, title, pub_date, tagged_preorder) VALUES (?, ?, ?, 1)",
        ("short", "Book", "2030-01-01"),
    )
    anomalies.log_anomalies()
    rows = fetch_anomalies(conn)
    assert rows == [{"isbn": "short", "reason": "Missing or malformed ISBN"}]


def test_detect_tagged_after_release(conn):
    today = date.today().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO preorders (isbn, title, pub_date, tagged_preorder) VALUES (?, ?, ?, 1)",
        ("4444444444444", "Book", today),
    )
    conn.execute("INSERT INTO releases (isbn) VALUES ('4444444444444')")
    anomalies.log_anomalies()
    rows = fetch_anomalies(conn)
    assert rows == [{"isbn": "4444444444444", "reason": "Tagged preorder after release"}]


def test_no_duplicate_logs(conn):
    old_date = (date.today() - timedelta(days=40)).strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO preorders (isbn, title, pub_date, tagged_preorder) VALUES (?, ?, ?, 1)",
        ("5555555555555", "Book", old_date),
    )
    anomalies.log_anomalies()
    anomalies.log_anomalies()
    cur = conn.execute(
        "SELECT COUNT(*) as c FROM anomalies_log WHERE isbn='5555555555555' AND reason='pub_date older than 30 days'"
    )
    count = cur.fetchone()[0]
    assert count == 1
