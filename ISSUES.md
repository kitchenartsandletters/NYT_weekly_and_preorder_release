# Issues and Tasks

## Critical Issues

- [ ] **Fix Preorder History Updates**: Ensure preorder history is consistently updated and changes are committed to the repository

- [x] **Missing Order Records**: Identify the 29 orders missing from reports and determine causes

## High Priority Issues

- [ ] **Data Validation**
  - Implement validation for preorder quantities to prevent negative values
  - Add validation alerts for unusual order volumes
  - Implement comparison with previous week's data

- [ ] **Error Handling**
  - Improve error reporting for API failures
  - Standardize logging format across all scripts
  - Enhance handling of edge cases in preorder processing

## Medium Priority Issues

- [ ] **Report Improvements**
  - Create summary section with totals and metrics
  - Implement detection of anomalous sales patterns
  - Add preorder release list to email notification

- [ ] **Workflow Automation**
  - Automate the process of removing released books from preorder collection
  - Implement automatic shipping profile updates after reporting
  - Consider daily shipper email for manual shipping adjustments since shipping profiles don't have a Shopify endpoint

- [ ] **Testing Framework**
  - Create integration test suite for workflows
  - Add unit tests for core functions
  - Develop test fixtures with sample data

- [ ] **Preorder Process**
  - Add reporting of skipped preorders for debugging
  - Implement cleanup function for test data in history file

## Completed Items

- [x] **Preorder Display Improvements**
  - Inventory quantities now display in approval issues
  - Publication dates appear in human-readable format (Month DD, YYYY)
  - Preorder sales successfully pass to weekly report

- [x] **Error Handling Enhancements**
  - Implemented exponential backoff for retries
  - Added handling for additional exception types

- [x] **Quantity Reconciliation** 
  - Debugged aggregation logic
  - Eliminated duplicate order processing
  - Resolved specific discrepancies between automated and manual reports

## Future Enhancements

- [ ] **Workflow Automation**
  - Automate email distribution of reports
  - Schedule weekly runs using GitHub Actions

- [ ] **Analytics Platform**
  - Implement alerting system for sales anomalies
  - Create dashboard for monitoring preorder conversion

  - [ ] **Manual Workflow**
  - Migrate GitHub Issues approval feature to dashboard integrated feature