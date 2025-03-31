# Shopify Sales Report

## Overview
This script fetches Shopify orders within a specified date range using the GraphQL API, maps variants to barcodes, accumulates quantities, and exports the data to a CSV report. It also handles preorder management through a two-phase workflow.

## Current Status
- **Preorder Flow:** Successfully identifies preorders ready for release, creates GitHub issues for approval, and processes approved preorders into the weekly sales report
- **Weekly Report:** Generates sales report CSV with regular sales and approved preorders
- **Preorder History:** Tracks which preorders have been reported to prevent duplicates
- **Workflow Automation:** GitHub Actions workflow handles both identification and reporting phases

## Workflow Process
1. **Identify Preorders** (Friday)
   - Runs audit of publication dates to find books ready for release
   - Creates GitHub issue with books for approval
   - Issue displays inventory levels and formatted publication dates

2. **Generate Report** (Monday)
   - Processes any approved preorder issues
   - Adds approved preorders to weekly sales
   - Updates preorder history tracking
   - Generates and emails sales report

## Resolved Issues
- ✅ Preorder inventory levels now displaying in approval issues
- ✅ Publication dates display in human-friendly format (Month DD, YYYY)
- ✅ Preorder books approved through GitHub issues successfully pass to weekly report
- ✅ Preorder history tracking preserves record of reported preorders
- ✅ Automated workflow commits preorder history changes to repository

## Known Issues
1. **Missing Records (Original):**
   - Description: 29 orders are not being fetched.
   - Possible Causes:
     - Pagination errors.
     - API limitations or filters.
   - Actions to Take:
     - Investigate the missing orders' details.
     - Check if they fall outside the date range or have unique attributes.

2. **Quantity Discrepancies (Partially Resolved):**
   - Description: Some product quantities do not match manual reports.
   - Possible Causes:
     - Duplicate processing.
     - Incorrect aggregation logic.
   - Actions to Take:
     - Validate aggregation logic.
     - Ensure no duplicate orders are processed.

3. **Edge Case Handling:**
   - Description: Need better handling of edge cases in preorder processing.
   - Possible Causes:
     - Books with missing or malformed publication dates.
     - Books released during blackout periods.
   - Actions to Take:
     - Enhance error handling for malformed data.
     - Add logic for special handling periods.

## Next Steps
- **Enhance Logging:**
  - Implement more detailed logging for troubleshooting
  - Store logs for future reference

- **Refund Integration:**
  - Improve handling of refunds for preorders
  - Track refunded preorders in history

- **Testing Improvements:**
  - Add more comprehensive test cases
  - Create testing fixtures for common scenarios

- **Documentation:**
  - Create detailed operation guide
  - Document GitHub issue approval process
  - Provide examples of common workflows

## How to Run
```bash
# Identify preorders ready for release
python audit_publication_dates.py --output-releases ./output/pending_releases_$(date +%Y-%m-%d).json

# Run the weekly sales report (includes approved preorders)
python weekly_sales_report.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Manual preorder approval (if needed)
python preorder-manager.py process-issue --issue-file ./issue_body.txt
```

## Scripts Overview

### Main Scripts
1. **weekly_sales_report.py**
   - Generates weekly sales report from Shopify using GraphQL
   - Filters line items with barcodes beginning with 978
   - Integrates approved preorders into the sales report

2. **audit_publication_dates.py**
   - Checks for books ready to be released based on publication dates
   - Identifies preorders to include in next sales report
   - Creates JSON file with books pending approval

3. **process_approved_releases.py**
   - Processes approved preorders from GitHub issues
   - Updates preorder history tracking
   - Adds approved books to sales report

4. **preorder_history_tracker.py**
   - Manages tracking of preorders already reported
   - Prevents duplicate reporting of preorder books
   - Maintains history of reported preorders

### Utility Scripts
1. **env_loader.py**
   - Handles environment variable loading with better error checking
   - Supports test mode for running without API credentials

2. **preorder-manager.py**
   - Comprehensive script for managing preorder workflow
   - Supports manual operations when needed

### Supporting Files
- **preorder_history.json**
  - Tracks which preorders have been reported
  - Prevents duplicate reporting across weeks

- **pending_releases_*.json**
  - Contains books ready for release pending approval
  - Created by the audit script

- **approved_releases_*.json**
  - Contains books approved for release
  - Created from GitHub issue approvals

## GitHub Workflow
The repository includes a GitHub Actions workflow that automates both the identification and reporting processes:

- **Friday:** Runs the preorder identification process and creates approval issues
- **Monday:** Processes approvals and generates the weekly report

The workflow handles testing and production modes with appropriate error handling and debugging information.