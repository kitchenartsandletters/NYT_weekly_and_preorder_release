import os
import sqlite3
import sys
from datetime import date

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

from refactor.src import presales
from refactor.utils import db as db_utils


@pytest.fixture()
def conn(monkeypatch):
    sqlite = sqlite3.connect(':memory:')
    sqlite.row_factory = sqlite3.Row
    sqlite.executescript(
        """
        CREATE TABLE preorders (
            isbn TEXT PRIMARY KEY,
            pub_date TEXT
        );
        CREATE TABLE orders (
            order_id TEXT,
            isbn TEXT,
            qty INTEGER,
            order_date TEXT
        );
        CREATE TABLE presales_log (
            isbn TEXT PRIMARY KEY,
            presale_qty INTEGER NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def fetch_presales(conn):
    return {
        r["isbn"]: r["presale_qty"]
        for r in conn.execute("SELECT isbn, presale_qty FROM presales_log").fetchall()
    }


def test_basic_sum(conn):
    conn.execute("INSERT INTO preorders (isbn, pub_date) VALUES (?, ?)", ("123", "2030-01-01"))
    conn.execute("INSERT INTO orders (order_id, isbn, qty, order_date) VALUES (?, ?, ?, ?)", ("o1", "123", 1, "2029-12-01"))
    conn.execute("INSERT INTO orders (order_id, isbn, qty, order_date) VALUES (?, ?, ?, ?)", ("o2", "123", 2, "2029-12-15"))
    presales.log_presales()
    assert fetch_presales(conn) == {"123": 3}


def test_ignore_after_pub_date(conn):
    conn.execute("INSERT INTO preorders (isbn, pub_date) VALUES (?, ?)", ("111", "2024-01-01"))
    conn.execute("INSERT INTO orders (order_id, isbn, qty, order_date) VALUES (?, ?, ?, ?)", ("o1", "111", 1, "2023-12-31"))
    conn.execute("INSERT INTO orders (order_id, isbn, qty, order_date) VALUES (?, ?, ?, ?)", ("o2", "111", 5, "2024-01-02"))
    presales.log_presales()
    assert fetch_presales(conn) == {"111": 1}


def test_skip_missing_preorder(conn):
    conn.execute("INSERT INTO orders (order_id, isbn, qty, order_date) VALUES (?, ?, ?, ?)", ("o1", "999", 1, "2030-01-01"))
    presales.log_presales()
    assert fetch_presales(conn) == {}


def test_update_existing_record(conn):
    conn.execute("INSERT INTO preorders (isbn, pub_date) VALUES (?, ?)", ("222", "2030-01-01"))
    conn.execute("INSERT INTO orders (order_id, isbn, qty, order_date) VALUES (?, ?, ?, ?)", ("o1", "222", 2, "2029-12-15"))
    conn.execute("INSERT INTO presales_log (isbn, presale_qty) VALUES (?, ?)", ("222", 1))
    presales.log_presales()
    rows = fetch_presales(conn)
    assert rows == {"222": 2}
    cur = conn.execute("SELECT COUNT(*) FROM presales_log WHERE isbn='222'")
    assert cur.fetchone()[0] == 1
