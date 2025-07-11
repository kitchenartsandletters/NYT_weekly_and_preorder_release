"""Sync preorder-tagged products from Shopify to the database.

This version accepts a list of product dicts (mockable for tests). Each dict
should include: isbn, title, vendor, pub_date (YYYY-MM-DD), tagged_preorder,
in_preorder_collection.
"""
from datetime import datetime
from typing import Iterable, Dict

from ..utils import db


def sync_preorders(products: Iterable[Dict]) -> None:
    """Insert or update preorder records using provided product data."""
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            for p in products:
                cur.execute(
                    """
                    INSERT INTO preorders (isbn, title, vendor, pub_date,
                                           tagged_preorder, in_preorder_collection)
                    VALUES (%(isbn)s, %(title)s, %(vendor)s, %(pub_date)s,
                            %(tagged_preorder)s, %(in_preorder_collection)s)
                    ON CONFLICT (isbn) DO UPDATE SET
                        title = EXCLUDED.title,
                        vendor = EXCLUDED.vendor,
                        pub_date = EXCLUDED.pub_date,
                        tagged_preorder = EXCLUDED.tagged_preorder,
                        in_preorder_collection = EXCLUDED.in_preorder_collection,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    {
                        "isbn": p["isbn"],
                        "title": p.get("title"),
                        "vendor": p.get("vendor"),
                        "pub_date": p.get("pub_date"),
                        "tagged_preorder": p.get("tagged_preorder", False),
                        "in_preorder_collection": p.get("in_preorder_collection", False),
                    },
                )
        conn.commit()
