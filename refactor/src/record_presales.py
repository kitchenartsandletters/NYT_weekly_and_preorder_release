"""Record preorder line item sales into the database."""
from datetime import datetime
from typing import Iterable, Dict

from ..utils import db


def record_presales(items: Iterable[Dict]) -> None:
    """Insert presale order line items."""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            for item in items:
                cur.execute(
                    """
                    INSERT INTO presales (isbn, order_id, qty, order_date)
                    VALUES (%(isbn)s, %(order_id)s, %(qty)s, %(order_date)s)
                    ON CONFLICT DO NOTHING;
                    """,
                    {
                        "isbn": item["isbn"],
                        "order_id": item["order_id"],
                        "qty": item.get("qty", 1),
                        "order_date": item.get("order_date", datetime.utcnow()),
                    },
                )
        conn.commit()
