# NYT Bestseller Reporting System

## Overview
This system automates the reporting of book sales to The New York Times Bestseller List. It handles regular sales data extraction from Shopify, preorder management, and weekly report generation through a two-phase workflow process.

## Key Features
- **Regular Sales Reporting**: Extracts sales data from Shopify using GraphQL API
- **Preorder Management**: Tracks, approves, and processes preorders with publication date control
- **Refund Handling**: Automatically adjusts quantities for refunded orders
- **Validation & Filtering**: Ensures only ISBNs (barcodes starting with 978/979) are included
- **Weekly Reporting**: Generates CSV reports with proper formatting for NYT requirements
- **Email Distribution**: Automatically emails reports to stakeholders

## Current Status
- ✅ **Preorder Approval Workflow**: Identifies preorders for release, creates GitHub issues, processes approvals
- ✅ **Weekly Report Generation**: Creates sales report CSVs with proper formatting
- ❌ **Preorder History Tracking**: History updates and repository commits need fixes
- ✅ **Email Distribution**: Automatically sends reports to stakeholders

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

## Setup Requirements
- Python 3.9+
- Shopify Admin API access credentials
- SendGrid API credentials for email delivery
- Environment variables configured in `.env.production` file

## Key Components

### Main Scripts
1. **weekly_sales_report.py**
   - Generates weekly sales report from Shopify using GraphQL
   - Filters line items with barcodes beginning with 978/979
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

## How to Run
```bash
# Identify preorders ready for release (Run on Friday)
python audit_publication_dates.py --output-releases ./output/pending_releases_$(date +%Y-%m-%d).json

# Run the weekly sales report (Run on Monday, includes approved preorders)
python weekly_sales_report.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Manual preorder approval (if needed)
python preorder-manager.py process-issue --issue-file ./issue_body.txt
```

## GitHub Workflow
The repository includes a GitHub Actions workflow that automates both the identification and reporting processes:

- **Friday**: Runs the preorder identification process and creates approval issues
- **Monday**: Processes approvals and generates the weekly report

## Resolved Issues
- ✅ **Preorder Display Improvements**: Inventory quantities and human-readable publication dates now shown in approval issues
- ✅ **Sales Integration**: Preorder sales successfully pass to weekly report

## Current Issues
- ❌ **Preorder History Updates**: History not being properly updated
- ❌ **Repository Integration**: History changes not being committed to repository

## Known Issues
See [ISSUES.md](./ISSUES.md) for current issues and planned improvements.

## Feature Roadmap
See [FEATURES.md](./FEATURES.md) for upcoming features and enhancements.