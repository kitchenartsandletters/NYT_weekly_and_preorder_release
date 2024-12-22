# Shopify Sales Report

## Overview
This script fetches Shopify orders within a specified date range using the GraphQL API, maps variants to barcodes, accumulates quantities, and exports the data to a CSV report.

## Current Status
- **Fetched Orders:** 418
- **Missing Records:** 29
- **Discrepancies:** Some quantities are inaccurate compared to manual reports.

## Known Issues
1. **Missing Records:**
   - Description: 29 orders are not being fetched.
   - Possible Causes:
     - Pagination errors.
     - API limitations or filters.
   - Actions to Take:
     - Investigate the missing orders' details.
     - Check if they fall outside the date range or have unique attributes.

2. **Quantity Discrepancies:**
   - Description: Some product quantities do not match manual reports.
   - Possible Causes:
     - Duplicate processing.
     - Incorrect aggregation logic.
   - Actions to Take:
     - Validate aggregation logic.
     - Ensure no duplicate orders are processed.

## Next Steps
- **Investigate Missing Records:**
  - Identify patterns or commonalities among missing orders.
  - Enhance the GraphQL query to ensure all relevant orders are fetched.

- **Resolve Quantity Discrepancies:**
  - Implement more robust aggregation checks.
  - Add detailed logging for discrepancies.

- **Enhance Error Handling:**
  - Implement retries with exponential backoff.
  - Handle more specific exceptions.

## How to Run
```bash
python weekly_sales_report.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Example formula used in Google Sheets to verify matching barcodes between
# the manual generated report (columns A:B) and the automated (columns F:G):
#
# =IF(ISERROR(VLOOKUP(A2, F:G, 2, FALSE)), 
#     "Missing in Automated", 
#     IF(VLOOKUP(A2, F:G, 2, FALSE) = B2, "Match", "Quantity Mismatch")
# )
#
# We also used =ABS(NewQty - OldQty) to compare quantity differences.