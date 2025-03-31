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

def find_latest_approved_releases(base_dir=None):
    """Find the most recent approved releases file"""
    import os
    import logging
    
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    output_dir = os.path.join(base_dir, 'output')
    
    if not os.path.exists(output_dir):
        logging.warning(f"Output directory does not exist: {output_dir}")
        return None, False
    
    # Find approved_releases files
    approval_files = [f for f in os.listdir(output_dir) if f.startswith('approved_releases_') and f.endswith('.json')]
    
    if not approval_files:
        logging.info("No approved releases files found")
        return None, False
    
    # Sort by filename (which contains date) to get the most recent
    approval_files.sort(reverse=True)
    latest_file = os.path.join(output_dir, approval_files[0])
    
    # Check if file has already been processed
    processed_marker = latest_file + '.processed'
    if os.path.exists(processed_marker):
        logging.info(f"Latest approval file has already been processed: {latest_file}")
        return latest_file, True
    
    return latest_file, False

def process_approved_releases(sales_data=None, base_dir=None):
    """
    Process approved releases and add to sales data
    
    Args:
        sales_data: Dictionary mapping ISBNs to quantities (optional)
        base_dir: Base directory for the project (optional, unused)
        
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
        history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'preorders', 'preorder_history.json')
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
        except Exception as e:
            logging.error(f"Error loading preorder history: {e}")
            # Default to empty history if file not found or invalid
            history_data = {"reported_preorders": []}
        
        # Track new books added to the report
        newly_reported_books = []
        skipped_books = []
        
        # Add approved books to sales data
        for book in approved_books:
            isbn = book.get('isbn')
            quantity = book.get('quantity', 0)
            
            if isbn and quantity > 0:
                # Add to sales data regardless of previous reporting
                # This ensures all approved books are included in the final report
                sales_data[isbn] = sales_data.get(isbn, 0) + quantity
                logging.info(f"Added {quantity} copies of ISBN {isbn} from approved releases")
                
                # Check if this ISBN has already been reported for tracking purposes
                already_reported = False
                for reported in history_data.get('reported_preorders', []):
                    if reported.get('isbn') == isbn:
                        already_reported = True
                        skipped_books.append({
                            'isbn': isbn,
                            'title': book.get('title', 'Unknown'),
                            'quantity': quantity,
                            'prev_report_date': reported.get('report_date'),
                            'prev_quantity': reported.get('quantity')
                        })
                        break
                
                # Track for history update if not already reported
                if not already_reported:
                    newly_reported_books.append({
                        'isbn': isbn,
                        'quantity': quantity,
                        'title': book.get('title', 'Unknown')
                    })
        
        # Add newly reported books to history (skip for test data)
        if newly_reported_books and not is_test_data:
            report_date = datetime.now().strftime('%Y-%m-%d')
            
            # Update history data directly
            for book in newly_reported_books:
                history_data['reported_preorders'].append({
                    'isbn': book['isbn'],
                    'quantity': book['quantity'],
                    'title': book.get('title', 'Unknown Title'),
                    'report_date': report_date,
                    'added': datetime.now().isoformat()
                })
            
            # Update last_updated timestamp
            history_data['last_updated'] = datetime.now().isoformat()
            
            # Save updated history
            try:
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(history_data, f, indent=2)
                logging.info(f"Updated preorder history with {len(newly_reported_books)} new entries")
            except Exception as e:
                logging.error(f"Error saving preorder history: {e}")
                
        elif newly_reported_books and is_test_data:
            logging.info(f"SKIPPING addition of {len(newly_reported_books)} books to preorder history because this is test data")
        
        # Mark file as processed only if not test data and not already processed
        if not is_test_data and not already_processed:
            processed_marker = latest_file + '.processed'
            with open(processed_marker, 'w') as f:
                f.write(datetime.now().isoformat())
            logging.info(f"Marked approval file as processed: {processed_marker}")
        
        # Log summary of processing
        logging.info(f"Processing summary:")
        logging.info(f"  - Total approved books: {len(approved_books)}")
        logging.info(f"  - Added to report: {len(approved_books)}")  # All approved books are added to sales data
        logging.info(f"  - New to history: {len(newly_reported_books)}")
        logging.info(f"  - Already in history: {len(skipped_books)}")
    
        # Log updated sales data at the end
        logging.info(f"Final sales data after processing approved releases: {sales_data}")
        
    except Exception as e:
        logging.error(f"Error processing approved releases: {e}")
        import traceback
        logging.error(traceback.format_exc())
    
    return sales_data

def verify_preorder_history_file():
    """
    Verifies that the preorder history file exists and has valid structure.
    Creates it if missing, repairs it if invalid.
    """
    logging.info("Verifying preorder history file...")
    
    # Get the path to the preorder history file
    history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    history_dir = os.path.dirname(history_file)
    
    # Ensure directory exists
    if not os.path.exists(history_dir):
        logging.info(f"Creating preorders directory: {history_dir}")
        os.makedirs(history_dir, exist_ok=True)
    
    # Check if file exists
    if not os.path.exists(history_file):
        logging.warning(f"Preorder history file does not exist: {history_file}")
        
        # Create default structure
        default_history = {
            "reported_preorders": [],
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(default_history, f, indent=2)
            logging.info(f"Created new preorder history file with default structure")
            return True
        except Exception as e:
            logging.error(f"Error creating preorder history file: {e}")
            return False
    
    # File exists, check if it's valid JSON
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
            
        # Verify structure
        if not isinstance(history_data, dict):
            raise ValueError("History data is not a dictionary")
            
        if "reported_preorders" not in history_data:
            raise ValueError("Missing 'reported_preorders' key")
            
        if not isinstance(history_data["reported_preorders"], list):
            raise ValueError("'reported_preorders' is not a list")
            
        # File is valid
        logging.info(f"Preorder history file is valid with {len(history_data['reported_preorders'])} entries")
        return True
        
    except json.JSONDecodeError as e:
        logging.error(f"Preorder history file contains invalid JSON: {e}")
        
        # Create backup of invalid file
        backup_file = f"{history_file}.invalid.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            with open(history_file, 'r') as src, open(backup_file, 'w') as dst:
                dst.write(src.read())
            logging.info(f"Created backup of invalid file: {backup_file}")
        except Exception as backup_error:
            logging.error(f"Error creating backup: {backup_error}")
        
        # Create new file with default structure
        default_history = {
            "reported_preorders": [],
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(default_history, f, indent=2)
            logging.info(f"Repaired preorder history file with default structure")
            return True
        except Exception as repair_error:
            logging.error(f"Error repairing history file: {repair_error}")
            return False
    
    except Exception as e:
        logging.error(f"Error validating preorder history file: {e}")
        return False

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