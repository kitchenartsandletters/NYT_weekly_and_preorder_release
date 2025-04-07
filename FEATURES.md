# Feature Roadmap

This document outlines the current and planned features for the NYT Bestseller Reporting System.

## Current Features

### Sales Data Processing
- ✅ Shopify GraphQL API integration for order data extraction
- ✅ Date range selection for weekly report periods
- ✅ ISBN-based filtering (978/979 barcodes)
- ✅ Refund handling and quantity adjustment

### Preorder Management
- ✅ Publication date tracking for preorder items
- ✅ Preorder collection identification in Shopify
- ❌ Preorder history tracking (needs fixes for updates and repository commits)
- ✅ Approval workflow through GitHub issues

### Report Generation
- ✅ CSV export with proper formatting for NYT requirements
- ✅ Exclusion reporting for skipped items
- ✅ Weekly scheduling based on NYT reporting windows
- ✅ Email delivery with detailed summaries

### Error Handling
- ✅ Exponential backoff for API retries
- ✅ Exception handling for common failure points
- ✅ Detailed logging of operations and errors

## Planned Features (Q2 2025)

### Error Handling & Data Validation
- [ ] Data validation for preorder quantities (prevent negative values)
- [ ] Validation alerts for unusual order volumes
- [ ] Comparison with previous week's data
- [ ] Standardized logging format across all scripts

### Reporting Enhancements
- [ ] Summary section with totals and metrics
- [ ] Anomalous sales pattern detection
- [ ] Add preorder release list to email notification
- [ ] Interactive dashboard for sales trends

### Post-Reporting Automation
- [ ] Automate removal of reported books from preorder collection
- [ ] Implement automatic shipping profile updates
- [ ] Create daily shipper email for manual adjustments needed

### Workflow Automation
- [ ] Fully automated end-to-end process
- [ ] Slack/Teams notifications for approvals and issues
- [ ] Mobile-friendly approval interface
- [ ] Integration with CRM for customer insights

### Data Quality
- [ ] Advanced validation rules for data integrity
- [ ] Anomaly detection and alerting
- [ ] Data reconciliation with third-party systems
- [ ] Historical trend analysis and forecasting

## Future Considerations (Q3-Q4 2025)

### Platform Expansion
- [ ] Support for additional sales channels (beyond Shopify)
- [ ] International reporting capabilities
- [ ] Integration with publisher reporting systems
- [ ] API for third-party integrations

### Analytics
- [ ] Sales performance prediction models
- [ ] Regional sales analysis and mapping
- [ ] Category and genre performance tracking
- [ ] Author and publisher dashboards

### System Infrastructure
- [ ] Containerized deployment with Docker
- [ ] Database backend for historical data
- [ ] Microservice architecture for scalability
- [ ] Role-based access control for team members

## Priority Matrix

| Feature | Impact | Effort | Priority | Timeframe |
|---------|--------|--------|----------|-----------|
| Fix Preorder History Updates | High | Medium | 1 | Immediate |
| Fix Repository Integration | High | Low | 2 | Immediate |
| Data Validation for Quantities | High | Medium | 3 | Q2 2025 |
| Add Preorder Release List to Email | High | Low | 4 | Q2 2025 |
| Automate Post-Reporting Process | High | Medium | 5 | Q2 2025 |
| Anomaly Detection | High | High | 6 | Q2 2025 |
| Summary Reporting | Medium | Medium | 7 | Q2 2025 |
| Testing Framework | Medium | High | 8 | Q2 2025 |