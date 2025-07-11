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

from refactor.src import readiness
from refactor.utils import db as db_utils


@pytest.fixture()
def conn(monkeypatch):
    sqlite = sqlite3.connect(':memory:')
    sqlite.row_factory = sqlite3.Row
    sqlite.executescript(
        """
        CREATE TABLE preorders (
            isbn TEXT PRIMARY KEY,
            pub_date TEXT,
            tagged_preorder BOOLEAN DEFAULT 0,
            in_preorder_collection BOOLEAN DEFAULT 0
        );
        CREATE TABLE presales (
            id TEXT PRIMARY KEY,
            isbn TEXT,
            qty INTEGER,
            order_date TEXT
        );
        CREATE TABLE releases (
            isbn TEXT PRIMARY KEY
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


def test_ready_title(conn):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    conn.execute("INSERT INTO preorders (isbn, pub_date, tagged_preorder) VALUES (?, ?, 1)", ("111", yesterday))
    conn.execute("INSERT INTO presales (id, isbn, qty) VALUES ('1', '111', 2)")
    result = readiness.analyze_readiness()
    assert result == ["111"]


def test_exclude_no_presales(conn):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    conn.execute("INSERT INTO preorders (isbn, pub_date, tagged_preorder) VALUES (?, ?, 1)", ("222", yesterday))
    result = readiness.analyze_readiness()
    assert result == []


def test_exclude_future_pub_date(conn):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    conn.execute("INSERT INTO preorders (isbn, pub_date, tagged_preorder) VALUES (?, ?, 1)", ("333", tomorrow))
    conn.execute("INSERT INTO presales (id, isbn, qty) VALUES ('2', '333', 1)")
    result = readiness.analyze_readiness()
    assert result == []


def test_exclude_missing_preorder(conn):
    conn.execute("INSERT INTO presales (id, isbn, qty) VALUES ('3', '999', 1)")
    result = readiness.analyze_readiness()
    assert result == []


def test_exclude_already_released(conn):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    conn.execute("INSERT INTO preorders (isbn, pub_date, tagged_preorder) VALUES (?, ?, 1)", ("444", yesterday))
    conn.execute("INSERT INTO presales (id, isbn, qty) VALUES ('4', '444', 1)")
    conn.execute("INSERT INTO releases (isbn) VALUES ('444')")
    result = readiness.analyze_readiness()
    assert result == []


def test_malformed_date_warning(conn, capsys):
    conn.execute("INSERT INTO preorders (isbn, pub_date, tagged_preorder) VALUES (?, ?, 1)", ("555", 'bad-date'))
    conn.execute("INSERT INTO presales (id, isbn, qty) VALUES ('5', '555', 1)")
    result = readiness.analyze_readiness()
    captured = capsys.readouterr()
    assert result == []
    assert "malformed" in captured.out.lower() or "invalid" in captured.out.lower()
