"""Record order cancellations from Shopify."""
from datetime import datetime
from typing import Dict

from ..utils import db


def record_cancellation(order_data: Dict) -> bool:
    """Log cancelled order items into ``cancellation_log``.

    Parameters
    ----------
    order_data: Dict
        Shopify order payload for a cancelled order.

    Returns
    -------
    bool
        ``True`` if rows inserted, ``False`` otherwise.
    """
    inserted = 0
    order_id = order_data.get("id") or order_data.get("order_id")
    cancelled_at = order_data.get("cancelled_at") or datetime.utcnow()
    line_items = order_data.get("line_items", [])
    if not order_id or not line_items:
        return False

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            for item in line_items:
                isbn = item.get("barcode") or item.get("isbn")
                quantity = item.get("quantity", 0)
                if not isbn or quantity <= 0:
                    continue
                cur.execute(
                    """
                    INSERT INTO cancellation_log (isbn, order_id, quantity, cancelled_on)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (order_id, isbn) DO NOTHING
                    """,
                    (isbn, order_id, quantity, cancelled_at),
                )
                inserted += cur.rowcount
        conn.commit()
    return inserted > 0
