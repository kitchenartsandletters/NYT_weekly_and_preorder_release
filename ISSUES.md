# Issues and Tasks

## Missing Records
- [ ] Identify the 29 missing orders.
- [ ] Determine if they fall outside the date range.
- [ ] Check for unique attributes that might exclude them.

## Quantity Discrepancies
- [x] Compare automated and manual reports to identify specific discrepancies.
- [ ] Debug the aggregation logic.
- [ ] Ensure no duplicate orders are processed.

## Error Handling Enhancements
- [x] Implement exponential backoff for retries.
- [x] Handle additional exception types.

## Documentation
- [x] Update `README.md` with new findings.
- [ ] Add comments to the script for clarity.

## Future Enhancements
- [ ] Automate email distribution of reports.
- [ ] Schedule the script to run weekly using GitHub Actions.

## Preorder Process
- [x] Ensure inventory quantities display in approval issues.
- [x] Format publication dates in human-readable format (Month DD, YYYY).
- [x] Fix preorder sales not being passed to weekly report.
- [x] Fix preorder history not being updated.
- [x] Fix preorder history changes not being committed to repository.

## New Issues
- [ ] Add data validation for preorder quantities to prevent negative values.
- [ ] Implement reporting of skipped preorders for debugging.
- [ ] Add cleanup function for removing test data from history file.
- [ ] Add better error reporting when API calls fail.
- [ ] Implement consistent logging format across all scripts.

## Weekly Report Improvements
- [ ] Create summary section in weekly report with totals and metrics.
- [ ] Add validation alerts for unusual order volumes.
- [ ] Add comparison with previous week's data.
- [ ] Implement detection of anomalous sales patterns.

## Testing and QA
- [ ] Create integration test suite for workflows.
- [ ] Add more unit tests for core functions.
- [ ] Create test fixtures with sample data.
- [ ] Document testing procedures for future maintenance.