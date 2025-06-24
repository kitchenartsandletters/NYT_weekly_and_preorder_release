"""Determine which preorder titles are eligible for release."""
from datetime import date
from typing import List, Dict

from ..utils import db


def analyze_readiness() -> List[Dict]:
    """Return preorders where pub_date has passed and not yet released."""
    today = date.today()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.* FROM preorders p
                LEFT JOIN releases r ON p.isbn = r.isbn
                WHERE p.pub_date <= %s AND r.isbn IS NULL
                """,
                (today,),
            )
            rows = cur.fetchall()
    return list(rows)
