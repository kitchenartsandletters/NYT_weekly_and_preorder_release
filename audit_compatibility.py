# DEPRECATED
"""
Compatibility module to ensure proper importing between audit and weekly report
This file exports symbols from weekly_sales_report.py that audit_publication_dates.py needs
"""

# Import all required functions from weekly_sales_report
from weekly_sales_report import (
    BASE_DIR,
    load_environment,
    fetch_product_details,
    run_query_with_retries,
    GRAPHQL_URL,
    HEADERS,
    load_pub_date_overrides,
    is_preorder_or_future_pub,
    calculate_total_preorder_quantities,
    get_product_ids_by_isbn
)

# Export these symbols
__all__ = [
    'BASE_DIR',
    'load_environment',
    'fetch_product_details',
    'run_query_with_retries',
    'GRAPHQL_URL',
    'HEADERS',
    'load_pub_date_overrides',
    'is_preorder_or_future_pub',
    'calculate_total_preorder_quantities',
    'get_product_ids_by_isbn'
]