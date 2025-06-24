"""Detect and log product metadata anomalies into ``anomalies_log``.

The ``log_anomalies`` function scans the ``preorders`` table for products still
tagged as preorder and validates a series of fields. Any issues discovered are
written to ``anomalies_log`` unless an identical entry (``isbn`` + ``reason``)
already exists. The goal is to surface bad or outdated data without spamming the
log on repeated runs.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Iterable

from ..utils import db


def is_valid_date(value: object) -> bool:
    """Return ``True`` if ``value`` is a ``YYYY-MM-DD`` date string or ``date``."""
    if isinstance(value, date):
        return True
    if not value:
        return False
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except Exception:
        return False


def is_valid_isbn(value: object) -> bool:
    """Return ``True`` if ``value`` is a 13 digit numeric string."""
    return bool(re.fullmatch(r"\d{13}", str(value or "")))


def log_anomalies() -> None:
    """Check preorder metadata for issues and insert log entries.

    Steps performed:

    1. Query all preorder-tagged products from ``preorders``.
    2. Validate fields for each product.
    3. Insert one row per anomaly into ``anomalies_log`` if not already present.
    """

    today = date.today()
    cutoff = today - timedelta(days=30)

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT isbn, pub_date, tagged_preorder, in_preorder_collection "
                "FROM preorders WHERE tagged_preorder = TRUE"
            )
            products: Iterable[dict] = cur.fetchall()

            cur.execute("SELECT isbn, reason FROM anomalies_log")
            existing = {(row["isbn"], row["reason"]) for row in cur.fetchall()}

            cur.execute("SELECT isbn FROM releases")
            released = {row["isbn"] for row in cur.fetchall()}

            for product in products:
                prod = dict(product)
                isbn = prod["isbn"]
                reasons = []

                pub_date_val = prod.get("pub_date")
                if not pub_date_val:
                    reasons.append("Missing pub_date")
                elif not is_valid_date(pub_date_val):
                    reasons.append("Malformed pub_date")
                else:
                    pd = (
                        pub_date_val
                        if isinstance(pub_date_val, date)
                        else datetime.strptime(str(pub_date_val), "%Y-%m-%d").date()
                    )
                    if pd < cutoff:
                        reasons.append("pub_date older than 30 days")

                if not is_valid_isbn(isbn):
                    reasons.append("Missing or malformed ISBN")

                if isbn in released and prod.get("tagged_preorder"):
                    reasons.append("Tagged preorder after release")

                for reason in reasons:
                    if (isbn, reason) not in existing:
                        cur.execute(
                            "INSERT INTO anomalies_log (isbn, reason) VALUES (%s, %s)",
                            (isbn, reason),
                        )
                        existing.add((isbn, reason))
        conn.commit()
