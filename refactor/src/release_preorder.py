"""Utilities for finalizing preorder releases."""
from __future__ import annotations

from datetime import date

from typing import Optional

from ..utils import db


def release_preorder(isbn: str, approver: str) -> bool:
    """Release a preorder product and log the snapshot.

    Parameters
    ----------
    isbn:
        The ISBN identifier for the product.
    approver:
        Slack username or identifier of the approver.

    Returns
    -------
    bool
        ``True`` if the release succeeded, ``False`` otherwise.
    """

    with db.get_connection() as conn:
        try:
            with conn.cursor() as cur:
                # Abort if already released
                cur.execute("SELECT 1 FROM releases_log WHERE isbn = %s", (isbn,))
                if cur.fetchone():
                    return False

                # Fetch preorder metadata
                cur.execute(
                    "SELECT tagged_preorder, in_preorder_collection, "
                    "COALESCE(inventory, 0) AS inventory FROM preorders WHERE isbn = %s",
                    (isbn,),
                )
                row = cur.fetchone()
                if not row:
                    return False

                if not row["tagged_preorder"]:
                    return False

                inventory = row["inventory"] if "inventory" in row.keys() else 0

                cur.execute(
                    "SELECT presale_qty FROM presales_log WHERE isbn = %s",
                    (isbn,),
                )
                presale_row = cur.fetchone()
                presale_total = presale_row["presale_qty"] if presale_row else 0

                # Update preorder flags
                cur.execute(
                    "UPDATE preorders SET tagged_preorder = FALSE, "
                    "in_preorder_collection = FALSE WHERE isbn = %s",
                    (isbn,),
                )

                # Insert release record
                cur.execute(
                    """
                    INSERT INTO releases_log (
                        isbn, released_on, approved_by, inventory_on_release, total_presales
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (isbn) DO NOTHING
                    """,
                    (isbn, date.today(), approver, inventory, presale_total),
                )
            conn.commit()
            return True
        except Exception as exc:  # pragma: no cover - safeguard
            conn.rollback()
            print(f"Error releasing {isbn}: {exc}")
            return False
