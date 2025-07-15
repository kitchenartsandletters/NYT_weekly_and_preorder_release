import os
import sqlite3
import sys

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

from refactor.src.release_preorder import release_preorder
from refactor.utils import db as db_utils


@pytest.fixture()
def conn(monkeypatch):
    sqlite = sqlite3.connect(':memory:')
    sqlite.row_factory = sqlite3.Row
    sqlite.executescript(
        """
        CREATE TABLE preorders (
            isbn TEXT PRIMARY KEY,
            tagged_preorder BOOLEAN DEFAULT 0,
            in_preorder_collection BOOLEAN DEFAULT 0,
            inventory INTEGER DEFAULT 0
        );
        CREATE TABLE presales_log (
            isbn TEXT PRIMARY KEY,
            presale_qty INTEGER NOT NULL
        );
        CREATE TABLE releases_log (
            isbn TEXT PRIMARY KEY,
            released_on DATE,
            approved_by TEXT,
            inventory_on_release INTEGER,
            total_presales INTEGER
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

        def executemany(self, query, seq):
            query = query.replace("%s", "?")
            return self._cur.executemany(query, seq)

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


def test_successful_release(conn):
    conn.execute(
        "INSERT INTO preorders (isbn, tagged_preorder, in_preorder_collection, inventory) VALUES (?, 1, 1, 5)",
        ("123",),
    )
    conn.execute(
        "INSERT INTO presales_log (isbn, presale_qty) VALUES (?, ?)",
        ("123", 7),
    )
    result = release_preorder("123", "alice")
    assert result is True
    row = conn.execute("SELECT tagged_preorder, in_preorder_collection FROM preorders WHERE isbn='123'").fetchone()
    assert row[0] == 0 and row[1] == 0
    release_row = conn.execute(
        "SELECT approved_by, inventory_on_release, total_presales FROM releases_log WHERE isbn='123'"
    ).fetchone()
    assert tuple(release_row) == ("alice", 5, 7)


def test_already_released(conn):
    conn.execute("INSERT INTO preorders (isbn, tagged_preorder) VALUES (?, 1)", ("111",))
    conn.execute("INSERT INTO releases_log (isbn, released_on, approved_by, inventory_on_release, total_presales) VALUES (?, '2024-01-01', 'bob', 0, 0)", ("111",))
    result = release_preorder("111", "alice")
    assert result is False


def test_missing_isbn(conn):
    result = release_preorder("999", "alice")
    assert result is False


def test_db_state_after_release(conn):
    conn.execute("INSERT INTO preorders (isbn, tagged_preorder, in_preorder_collection) VALUES (?, 1, 1)", ("222",))
    result = release_preorder("222", "alice")
    assert result is True
    # ensure release record exists and preorders updated
    r = conn.execute("SELECT * FROM releases_log WHERE isbn='222'").fetchone()
    assert r is not None
    p = conn.execute("SELECT tagged_preorder, in_preorder_collection FROM preorders WHERE isbn='222'").fetchone()
    assert p[0] == 0 and p[1] == 0
