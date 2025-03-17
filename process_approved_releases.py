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

def process_approved_releases(sales_data, base_dir):
    # Log initial sales data
    logging.info(f"Initial sales data before processing approved releases: {len(sales_data)} items")
    logging.info("=" * 50)
    logging.info("PROCESS APPROVED RELEASES FUNCTION CALLED")
    logging.info(f"Base directory: {base_dir}")
    
    # Enhanced directory checking and creation
    preorders_dir = os.path.join(base_dir, 'preorders')
    if not os.path.exists(preorders_dir):
        logging.info(f"Creating missing preorders directory: {preorders_dir}")
        os.makedirs(preorders_dir, exist_ok=True)
    
    # Check for history file with more fallback options
    history_file = os.path.join(base_dir, 'preorders', 'preorder_history.json')
    logging.info(f"Looking for history file at: {history_file}")
    
    # Check if history file exists
    if not os.path.exists(history_file):
        logging.warning(f"History file not found at primary location: {history_file}")
        
        # Try alternative locations
        alt_locations = [
            os.path.join(base_dir, 'preorder_history.json'),
            os.path.join(os.getcwd(), 'preorders', 'preorder_history.json'),
            os.path.join(os.getcwd(), 'preorder_history.json')
        ]
        
        for alt_location in alt_locations:
            logging.info(f"Checking alternative location: {alt_location}")
            if os.path.exists(alt_location):
                logging.info(f"Found history file at alternative location: {alt_location}")
                # Copy to expected location
                import shutil
                shutil.copy2(alt_location, history_file)
                logging.info(f"Copied history file to expected location: {history_file}")
                break
        
        # If still not found, create a new file
        if not os.path.exists(history_file):
            logging.warning("History file not found in any location, creating new file")
            # Create a simple template file
            history_data = {
                "reported_preorders": [],
                "last_updated": datetime.now().isoformat()
            }
            try:
                with open(history_file, 'w') as f:
                    json.dump(history_data, f, indent=2)
                logging.info(f"Created new history file at: {history_file}")
            except Exception as e:
                logging.error(f"Failed to create new history file: {e}")
    
    # Show history file contents once we definitely have one
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history_content = f.read()
                logging.info(f"History file contents: {history_content}")
        except Exception as e:
            logging.error(f"Error reading history file: {e}")
    
    # Rest of the function remains the same
    approvals_file = get_latest_approvals_file(base_dir)
    
    if not approvals_file:
        logging.info("No unprocessed approval files found")
        return sales_data
    
    try:
        logging.info(f"Processing approved releases from: {approvals_file}")
        
        with open(approvals_file, 'r', encoding='utf-8') as f:
            approved_data = json.load(f)
        
        approved_books = approved_data.get('approved_releases', [])
        
        if not approved_books:
            logging.info("No approved books found in file")
            return sales_data
        
        logging.info(f"Found {len(approved_books)} approved books to include in report")
        
        # Load preorder history to check for duplicates
        history_data = load_preorder_history()
        
        # Enhanced error handling for history loading
        if not history_data:
            logging.warning("Could not load preorder history, creating empty history")
            history_data = {"reported_preorders": [], "last_updated": datetime.now().isoformat()}
        
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
        
        # Add newly reported books to history with enhanced error handling
        if newly_reported_books:
            try:
                report_date = datetime.now().strftime('%Y-%m-%d')
                batch_add_to_history(newly_reported_books, report_date)
                logging.info(f"Added {len(newly_reported_books)} books to preorder history")
            except Exception as e:
                logging.error(f"Error adding books to preorder history: {e}")
                # Continue execution despite history update error
        
        # Mark file as processed
        processed_marker = approvals_file + '.processed'
        with open(processed_marker, 'w') as f:
            f.write(datetime.now().isoformat())
        
        logging.info(f"Marked approval file as processed: {processed_marker}")
        
        # Log summary of processing
        logging.info(f"Processing summary:")
        logging.info(f"  - Total approved books: {len(approved_books)}")
        logging.info(f"  - Added to report: {len(newly_reported_books)}")
        logging.info(f"  - Skipped (already reported): {len(skipped_books)}")
        if skipped_books:
            for book in skipped_books:
                logging.info(f"    - Skipped: {book['title']} (ISBN: {book['isbn']}) - Previously reported on {book['prev_report_date']}")
    
        # Log updated sales data at the end
        logging.info(f"Final sales data after processing approved releases: {len(sales_data)} items")
        
    except Exception as e:
        logging.error(f"Error processing approved releases: {e}")
    
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