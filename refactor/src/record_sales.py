"""Record non-preorder book sales into the database."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable

from ..utils import db


def _extract_items(order_data: Dict) -> Iterable[Dict]:
    """Yield simplified line item data from a Shopify order payload."""
    order_id = order_data.get("id") or order_data.get("order_id")
    order_date = order_data.get("created_at") or order_data.get("order_date") or datetime.utcnow()
    for item in order_data.get("line_items", []):
        yield {
            "isbn": item.get("barcode") or item.get("isbn"),
            "quantity": item.get("quantity", 1),
            "order_id": order_id,
            "order_date": order_date,
        }


def record_sales(order_data: Dict) -> bool:
    """Insert non-preorder line items into ``sales_log``.

    Parameters
    ----------
    order_data: Dict
        Shopify order payload.

    Returns
    -------
    bool
        ``True`` if any rows were inserted, ``False`` otherwise.
    """

    inserted = 0
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT isbn FROM preorders")
            preorder_isbns = {row["isbn"] for row in cur.fetchall()}

            for item in _extract_items(order_data):
                isbn = item.get("barcode") or item.get("isbn")
                if not isbn or isbn in preorder_isbns:
                    continue

                cur.execute(
                    """
                    INSERT INTO sales_log (isbn, order_id, quantity, order_date)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (order_id, isbn) DO NOTHING
                    """,
                    (isbn, item["order_id"], item["quantity"], item["order_date"]),
                )
                inserted += cur.rowcount
        conn.commit()
    return inserted > 0
