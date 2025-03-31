#!/usr/bin/env python
"""
Process approved releases for the weekly sales report

This module provides functions to include approved preorder titles in the weekly sales report
"""
import os
import json
import logging
from datetime import datetime

# Import the preorder history tracker
from preorder_history_tracker import load_preorder_history, is_preorder_reported, batch_add_to_history

def get_latest_approvals_file(base_dir):
    """Find the most recent approved releases file"""
    output_dir = os.path.join(base_dir, 'output')
    
    if not os.path.exists(output_dir):
        logging.warning(f"Output directory does not exist: {output_dir}")
        return None
    
    # Find approved_releases files
    approval_files = [f for f in os.listdir(output_dir) if f.startswith('approved_releases_') and f.endswith('.json')]
    
    if not approval_files:
        logging.info("No approved releases files found")
        return None
    
    # Sort by filename (which contains date) to get the most recent
    approval_files.sort(reverse=True)
    latest_file = os.path.join(output_dir, approval_files[0])
    
    # Check if file has already been processed
    processed_marker = latest_file + '.processed'
    if os.path.exists(processed_marker):
        logging.info(f"Latest approval file has already been processed: {latest_file}")
        return None
    
    return latest_file

def process_approved_releases(sales_data=None):
    """
    Process approved releases and add to sales data
    
    Args:
        sales_data: Dictionary mapping ISBNs to quantities (optional)
        
    Returns:
        Updated sales data with approved releases included
    """
    if sales_data is None:
        sales_data = {}
    
    # Log initial sales data
    logging.info(f"Initial sales data before processing approved releases: {sales_data}")
    
    # Find the latest approvals file
    latest_file, already_processed = find_latest_approved_releases()
    
    if not latest_file:
        logging.info("No approved releases files found")
        return sales_data
    
    try:
        logging.info(f"Processing approved releases from: {latest_file}")
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            approved_data = json.load(f)
        
        approved_books = approved_data.get('approved_releases', [])
        is_test_data = approved_data.get('test_data', False)
        
        if not approved_books:
            logging.info("No approved books found in file")
            return sales_data
        
        logging.info(f"Found {len(approved_books)} approved books to include in report")
        logging.info(f"Is test data: {is_test_data}")
        
        # Load preorder history to check for duplicates
        from preorder_history_tracker import load_preorder_history, is_preorder_reported, batch_add_to_history
        history_data = load_preorder_history()
        
        # Track new books added to the report
        newly_reported_books = []
        skipped_books = []
        
        # Add approved books to sales data
        for book in approved_books:
            isbn = book.get('isbn')
            quantity = book.get('quantity', 0)
            
            if isbn and quantity > 0:
                # Check if this ISBN has already been reported
                already_reported, record = is_preorder_reported(isbn, history_data)
                
                if already_reported:
                    # Skip this book as it's already been reported
                    logging.info(f"Skipping ISBN {isbn} - already reported on {record.get('report_date')} with quantity {record.get('quantity')}")
                    skipped_books.append({
                        'isbn': isbn,
                        'title': book.get('title', 'Unknown'),
                        'quantity': quantity,
                        'prev_report_date': record.get('report_date'),
                        'prev_quantity': record.get('quantity')
                    })
                else:
                    # Add to sales data and track for history
                    sales_data[isbn] = sales_data.get(isbn, 0) + quantity
                    logging.info(f"Added {quantity} copies of ISBN {isbn} from approved releases")
                    
                    newly_reported_books.append({
                        'isbn': isbn,
                        'quantity': quantity,
                        'title': book.get('title', 'Unknown')
                    })
        
        # Add newly reported books to history (skip for test data)
        if newly_reported_books and not is_test_data:
            report_date = datetime.now().strftime('%Y-%m-%d')
            updated_history = batch_add_to_history(newly_reported_books, report_date)
            logging.info(f"Added {len(newly_reported_books)} books to preorder history")
            
            # Log the updated preorder history for verification
            if updated_history:
                logging.info(f"Updated preorder history now has {len(updated_history.get('reported_preorders', []))} entries")
                logging.info(f"Last updated timestamp: {updated_history.get('last_updated')}")
            else:
                logging.warning("Failed to update preorder history")
                
        elif newly_reported_books and is_test_data:
            logging.info(f"SKIPPING addition of {len(newly_reported_books)} books to preorder history because this is test data")
        
        # Mark file as processed only if not test data and not already processed
        if not is_test_data and not already_processed:
            processed_marker = latest_file + '.processed'
            with open(processed_marker, 'w') as f:
                f.write(datetime.now().isoformat())
            logging.info(f"Marked approval file as processed: {processed_marker}")
        elif already_processed:
            logging.info(f"File was already marked as processed")
        else:
            logging.info(f"Skipping processed marker creation because this is test data")
        
        # Log summary of processing
        logging.info(f"Processing summary:")
        logging.info(f"  - Total approved books: {len(approved_books)}")
        logging.info(f"  - Added to report: {len(newly_reported_books)}")
        logging.info(f"  - Skipped (already reported): {len(skipped_books)}")
        if skipped_books:
            for book in skipped_books:
                logging.info(f"    - Skipped: {book['title']} (ISBN: {book['isbn']}) - Previously reported on {book['prev_report_date']}")
    
        # Log updated sales data at the end
        logging.info(f"Final sales data after processing approved releases: {sales_data}")
        
    except Exception as e:
        logging.error(f"Error processing approved releases: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    return sales_data

def initialize_preorder_history(preorders, report_date):
    """
    Initialize the preorder history with books that have already been reported
    
    Args:
        preorders: List of dicts with isbn, quantity (and optionally title)
        report_date: The date these preorders were reported (YYYY-MM-DD)
    """
    from preorder_history_tracker import initialize_history_with_reported_preorders
    initialize_history_with_reported_preorders(preorders, report_date)
    logging.info(f"Initialized preorder history with {len(preorders)} previously reported books")
    
# Example usage for initializing history with previously reported books
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    # Example of books that have already been reported
    previously_reported = [
        {"isbn": "9780593234778", "quantity": 8, "title": "Ghana to the World"},
        {"isbn": "9781984826213", "quantity": 5, "title": "Example Book 2"},
        {"isbn": "9780857521989", "quantity": 3, "title": "Example Book 3"}
    ]
    
    # The date when they were reported (previous weekly report)
    report_date = "2025-03-08"  # Format: YYYY-MM-DD
    
    # Initialize history with these books
    initialize_preorder_history(previously_reported, report_date)