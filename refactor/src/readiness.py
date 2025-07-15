"""Determine which preorder titles are eligible for release."""
from __future__ import annotations

from datetime import date, datetime
from typing import List

from ..utils import db


def analyze_readiness() -> List[str]:
    """Return a list of ISBNs ready for release."""
    today = date.today()
    ready: List[str] = []
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.isbn, p.pub_date, p.tagged_preorder, p.in_preorder_collection,
                       COALESCE(SUM(s.qty), 0) AS presale_qty,
                       r.isbn AS released
                FROM preorders p
                LEFT JOIN presales s ON p.isbn = s.isbn
                LEFT JOIN releases r ON p.isbn = r.isbn
                GROUP BY p.isbn, p.pub_date, p.tagged_preorder, p.in_preorder_collection, r.isbn
                """
            )
            rows = cur.fetchall()

            for row in rows:
                isbn = row["isbn"]
                pub_date_val = row["pub_date"]
                presale_qty = row["presale_qty"]
                tagged = row["tagged_preorder"]
                in_coll = row["in_preorder_collection"]
                released = row["released"]

                if released:
                    continue

                if pub_date_val is None:
                    print(f"Warning: missing pub_date for ISBN {isbn}")
                    continue

                if isinstance(pub_date_val, (datetime, date)):
                    pub_d = pub_date_val if isinstance(pub_date_val, date) else pub_date_val.date()
                else:
                    try:
                        pub_d = datetime.strptime(str(pub_date_val), "%Y-%m-%d").date()
                    except Exception:
                        print(f"Warning: malformed pub_date for ISBN {isbn}")
                        continue

                if pub_d > today:
                    continue

                if presale_qty <= 0:
                    continue

                if not tagged and not in_coll:
                    continue

                ready.append(isbn)
    return ready
