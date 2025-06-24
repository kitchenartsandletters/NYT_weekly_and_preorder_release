"""Utilities for aggregating and logging preorder presales."""
from __future__ import annotations

from typing import Dict, Iterable
from collections import defaultdict
from datetime import datetime, date

from ..utils import db


def log_presales() -> None:
    """Aggregate preorder quantities and upsert into ``presales_log``.

    Steps:
        1. Fetch orders referencing products still listed in ``preorders``.
        2. Count quantities for orders placed before the product ``pub_date``.
        3. Insert or update totals in ``presales_log`` keyed by ISBN.
    """

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.isbn, o.qty, o.order_date, p.pub_date
                FROM orders o
                JOIN preorders p ON o.isbn = p.isbn
                """
            )
            rows: Iterable[Dict] = cur.fetchall()

            totals: Dict[str, int] = defaultdict(int)
            for row in rows:
                isbn = row["isbn"]
                qty = row["qty"]
                order_dt = row["order_date"]
                pub_date = row["pub_date"]

                if pub_date is None:
                    # cannot determine presale window
                    continue

                # normalise to date objects
                if not isinstance(order_dt, (datetime, date)):
                    order_dt = datetime.fromisoformat(str(order_dt))
                if not isinstance(pub_date, (datetime, date)):
                    pub_date = datetime.fromisoformat(str(pub_date))

                if order_dt.date() >= pub_date.date():
                    continue

                totals[isbn] += qty

            for isbn, qty in totals.items():
                cur.execute(
                    """
                    INSERT INTO presales_log (isbn, presale_qty)
                    VALUES (%s, %s)
                    ON CONFLICT (isbn) DO UPDATE SET
                        presale_qty = EXCLUDED.presale_qty,
                        last_updated = CURRENT_TIMESTAMP
                    """,
                    (isbn, qty),
                )
        conn.commit()
