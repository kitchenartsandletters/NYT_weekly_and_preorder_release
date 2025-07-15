"""Record refund events from Shopify."""
from datetime import datetime
from typing import Dict

from ..utils import db


def record_refund(refund_data: Dict) -> bool:
    """Log refunded items into ``refund_log``.

    Parameters
    ----------
    refund_data: Dict
        Shopify order payload including ``refunds`` list.

    Returns
    -------
    bool
        ``True`` if rows inserted, ``False`` otherwise.
    """
    inserted = 0
    order_id = refund_data.get("id") or refund_data.get("order_id")
    refunds = refund_data.get("refunds", [])
    if not order_id or not refunds:
        return False

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            for refund in refunds:
                refund_date = refund.get("created_at") or datetime.utcnow()
                for item in refund.get("refund_line_items", []):
                    line = item.get("line_item", {})
                    isbn = line.get("barcode") or line.get("isbn")
                    quantity = item.get("quantity", 0)
                    if not isbn or quantity <= 0:
                        continue
                    cur.execute(
                        """
                        INSERT INTO refund_log (isbn, order_id, quantity, refund_date)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (order_id, isbn, refund_date) DO NOTHING
                        """,
                        (isbn, order_id, quantity, refund_date),
                    )
                    inserted += cur.rowcount
        conn.commit()
    return inserted > 0
