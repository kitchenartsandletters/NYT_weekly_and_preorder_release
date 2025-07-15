import os
import sqlite3
import sys
from datetime import datetime

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

from refactor.src.record_cancellation import record_cancellation
from refactor.utils import db as db_utils


@pytest.fixture()
def conn(monkeypatch):
    sqlite = sqlite3.connect(':memory:')
    sqlite.row_factory = sqlite3.Row
    sqlite.executescript(
        """
        CREATE TABLE cancellation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isbn TEXT,
            order_id TEXT,
            quantity INTEGER,
            cancelled_on TEXT,
            UNIQUE(order_id, isbn)
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


def fetch_cancellations(conn):
    return [dict(r) for r in conn.execute(
        "SELECT isbn, order_id, quantity FROM cancellation_log ORDER BY id"
    ).fetchall()]


def sample_payload(**overrides):
    data = {
        "id": "o1",
        "cancelled_at": "2030-01-03T00:00:00Z",
        "line_items": [
            {"barcode": "111", "quantity": 1},
            {"barcode": "222", "quantity": 2},
        ],
    }
    data.update(overrides)
    return data


def test_record_cancellation(conn):
    payload = sample_payload()
    inserted = record_cancellation(payload)
    assert inserted is True
    rows = fetch_cancellations(conn)
    assert rows == [
        {"isbn": "111", "order_id": "o1", "quantity": 1},
        {"isbn": "222", "order_id": "o1", "quantity": 2},
    ]


def test_dedup_cancellation(conn):
    payload = sample_payload()
    record_cancellation(payload)
    record_cancellation(payload)
    rows = fetch_cancellations(conn)
    assert len(rows) == 2

