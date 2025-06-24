"""Finalize preorder release by inserting into releases table."""
from typing import Optional
from datetime import date

from ..utils import db


def release_preorder(isbn: str, approved_by: Optional[str] = None, inventory: int = 0) -> None:
    """Mark a preorder as released and snapshot presales count."""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM presales WHERE isbn = %s",
                (isbn,)
            )
            presale_total = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO releases (isbn, released_on, approved_by, inventory_on_release, total_presales)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (isbn) DO NOTHING
                """,
                (isbn, date.today(), approved_by, inventory, presale_total),
            )
        conn.commit()
