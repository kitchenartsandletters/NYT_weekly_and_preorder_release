# Issues and Tasks

## Critical Issues

- [ ] **KIT-56: Implement Reliable Repository Commits for History Changes**
  **Description:** Changes to the preorder history file are not being committed to the repository, causing inconsistencies between local and remote versions.

  Tasks:
  - [ ] Debug repository commit process in GitHub workflow
  - [ ] Ensure proper Git credentials are available to workflow
  - [ ] Add verification step to confirm commits were successful
  - [ ] Implement notification for failed commits
  - [ ] Add documentation for manual recovery process
  - [ ] Add logging for all history update operations

## High Priority Issues

- [ ] **KIT-55: Automate Post-Report Process for Released Preorders**
  **Description:** After preorders are reported, several manual steps are still required. This should be automated.

  Tasks:
  - [x] Implement automatic removal of reported books from preorder collection
  - [ ] Create process to update shipping profiles after reporting
  - [ ] Develop daily email for shipping adjustments that cannot be automated
  - [ ] Add verification to confirm all post-reporting steps completed successfully
  - [ ] Create audit trail of automated actions

- [ ] **KIT-86: Adding verification feature to parse pending release data and revisit preorder overrides**
  **Description:** As preorder sales are accumulated, add the ability to parse presales quantities and titles. Allow overrides via Github Issue

  Tasks:
  - [ ] Add ability to search accumulated preorder presales
  - [ ] Add ability to override and force preorder release ahead of publisher ss date or adding missing presales quantities via GH issue with entry fields for ISBN and sales quantities

## Medium Priority Issues

- [ ] **KIT-54: Enhance Email Notifications with Preorder Release List**
  **Description:** Weekly report emails should include a clear list of preorders that were approved and included in the report.

  Tasks:
  - [ ] Modify `send_email()` function in `weekly_sales_report.py`
  - [ ] Format preorder release information in a readable table
  - [ ] Include publication dates and quantities for each released preorder
  - [ ] Add summary totals for preorder releases
  - [ ] Test email formatting across different email clients

- [ ] **KIT-36: Preorder Dashboard Integration**
  Tasks:
  - [ ] Create dashboard for monitoring preorder conversion
  - [ ] Migrate GitHub Issues to dashboard

- [ ] **KIT-30: Backup Plan**
  Tasks:
  - [ ] Ensure team members know how to manually trigger the workflows if needed
  - [ ] Document any manual override processes for emergencies

- [ ] **KIT-29: Set Up Monitoring**
  Tasks:
  - [x] Configure GitHub notifications for when approval issues are created
  - [ ] Establish a check to verify that the workflow ran successfully each week

- [ ] **KIT-28: Document the Process**
  Tasks:
  - [ ] Share the approval process with your team
  - [ ] Specify who is responsible for reviewing and approving preorder books
  - [ ] Set clear deadlines for approvals (before Monday morning)

- [ ] **KIT-88: Expand early stock email reporting with better inventory snapshots (future feature)**

- [ ] **KIT-89: Improve pub date and collection validation redundancy checks**

- [ ] **KIT-90: Rebuild audit_publication_dates.py for deeper override logic and faster preload of anomalies**

- [ ] **KIT-91: Automate refunds/reversals for preorders that are canceled (CSV reconciliation + lightweight webhook listening)**




## Future Enhancements

- [ ] **KIT-85: Manual Workflow**
  Tasks:
  - [ ] Migrate GitHub Issues approval feature to dashboard integrated feature

## Completed Items

- [x] **Missing Order Records**: Identify the 29 orders missing from reports and determine causes

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

- [x] **Workflow Automation**
  - Automated email distribution of reports
  - Scheduled weekly runs using GitHub Actions

- [x] **KIT-84: Add Logic to Detect Early Releases**
  **Description:** Book titles may be released ahead of their release date because:
  1) stock is delivered unexpectedly ahead of schedule
  2) publishers provide no restrictions on early sales

  Tasks:
  - [x] Let our system acknowledge books with positive inventory quantities (despite being in the Preorder collection, tagged 'preorder', etc) be nominated for the current weekly preorder release