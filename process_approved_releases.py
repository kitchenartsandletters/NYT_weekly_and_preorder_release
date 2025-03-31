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

def process_approved_releases(sales_data=None, base_dir=None):
    """
    Process approved releases and add to sales data
    
    Args:
        sales_data: Dictionary mapping ISBNs to quantities (optional)
        
    Returns:
        Updated sales data with approved releases included
    """
    if sales_data is None:
        sales_data = {}
    
    try:
        # Log initial sales data
        logging.info("=" * 50)
        logging.info("PROCESS APPROVED RELEASES FUNCTION STARTED")
        logging.info(f"Initial sales data: {sales_data}")
        
        # Find the latest approvals file
        try:
            latest_file, already_processed = find_latest_approved_releases()
            logging.info(f"Latest approval file: {latest_file}")
            logging.info(f"Already processed: {already_processed}")
        except Exception as e:
            logging.error(f"Error finding latest approvals file: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return sales_data
        
        if not latest_file:
            logging.info("No approved releases files found")
            return sales_data
        
        # Read the approvals file
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                file_content = f.read()
                logging.debug(f"File content (first 200 chars): {file_content[:200]}...")
                
                # Parse the JSON content
                approved_data = json.loads(file_content)
                logging.info(f"Successfully parsed JSON from {latest_file}")
                
                # Check if the parsed data has the expected structure
                if not isinstance(approved_data, dict):
                    logging.error(f"Parsed data is not a dictionary: {type(approved_data)}")
                    return sales_data
                
                if 'approved_releases' not in approved_data:
                    logging.error("'approved_releases' key missing from parsed data")
                    logging.debug(f"Available keys: {approved_data.keys()}")
                    return sales_data
        except FileNotFoundError:
            logging.error(f"Approvals file not found: {latest_file}")
            return sales_data
        except json.JSONDecodeError as e:
            logging.error(f"Error parsing JSON from {latest_file}: {e}")
            logging.error(f"First 200 chars of file: {file_content[:200]}")
            return sales_data
        except Exception as e:
            logging.error(f"Unexpected error reading approvals file: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return sales_data
        
        # Process the approved books
        approved_books = approved_data.get('approved_releases', [])
        is_test_data = approved_data.get('test_data', False)
        
        logging.info(f"Found {len(approved_books)} approved books to include in report")
        logging.info(f"Is test data: {is_test_data}")
        
        if not approved_books:
            logging.info("No approved books found in file")
            return sales_data
        
        # Load preorder history
        try:
            from preorder_history_tracker import load_preorder_history, is_preorder_reported, batch_add_to_history
            history_data = load_preorder_history()
            logging.info(f"Loaded preorder history with {len(history_data.get('reported_preorders', []))} entries")
        except Exception as e:
            logging.error(f"Error loading preorder history: {e}")
            import traceback
            logging.error(traceback.format_exc())
            # Continue with empty history data
            history_data = {"reported_preorders": []}
        
        # Track new books added to the report
        newly_reported_books = []
        skipped_books = []
        
        # Process each approved book
        for i, book in enumerate(approved_books):
            try:
                isbn = book.get('isbn')
                quantity = book.get('quantity', 0)
                title = book.get('title', f"Book {i+1}")
                
                logging.info(f"Processing book {i+1}/{len(approved_books)}: ISBN={isbn}, Title={title}, Quantity={quantity}")
                
                if not isbn:
                    logging.warning(f"Missing ISBN for book {i+1}: {book}")
                    continue
                    
                if not quantity or quantity <= 0:
                    logging.warning(f"Invalid quantity for ISBN {isbn}: {quantity}")
                    continue
                
                # Check if already reported
                already_reported, record = is_preorder_reported(isbn, history_data)
                
                if already_reported:
                    logging.info(f"Skipping ISBN {isbn} - already reported on {record.get('report_date')} with quantity {record.get('quantity')}")
                    skipped_books.append({
                        'isbn': isbn,
                        'title': title,
                        'quantity': quantity,
                        'prev_report_date': record.get('report_date'),
                        'prev_quantity': record.get('quantity')
                    })
                else:
                    # Add to sales data
                    sales_data[isbn] = sales_data.get(isbn, 0) + quantity
                    logging.info(f"Added {quantity} copies of ISBN {isbn} to sales data")
                    
                    newly_reported_books.append({
                        'isbn': isbn,
                        'quantity': quantity,
                        'title': title
                    })
            except Exception as book_error:
                logging.error(f"Error processing book {i+1}: {book_error}")
                continue
        
        # Update preorder history
        if newly_reported_books and not is_test_data:
            try:
                logging.info(f"Updating preorder history with {len(newly_reported_books)} books")
                report_date = datetime.now().strftime('%Y-%m-%d')
                updated_history = batch_add_to_history(newly_reported_books, report_date)
                
                if updated_history:
                    logging.info(f"Successfully updated preorder history")
                    logging.info(f"History now has {len(updated_history.get('reported_preorders', []))} entries")
                else:
                    logging.warning("Failed to update preorder history")
            except Exception as history_error:
                logging.error(f"Error updating preorder history: {history_error}")
                import traceback
                logging.error(traceback.format_exc())
        elif newly_reported_books and is_test_data:
            logging.info(f"SKIPPING addition of {len(newly_reported_books)} books to preorder history because this is test data")
        
        # Mark file as processed
        if not is_test_data and not already_processed:
            try:
                processed_marker = latest_file + '.processed'
                with open(processed_marker, 'w') as f:
                    f.write(datetime.now().isoformat())
                logging.info(f"Marked approval file as processed: {processed_marker}")
            except Exception as marker_error:
                logging.error(f"Error marking file as processed: {marker_error}")
        
        # Log summary
        logging.info(f"Processing summary:")
        logging.info(f"  - Total approved books: {len(approved_books)}")
        logging.info(f"  - Added to report: {len(newly_reported_books)}")
        logging.info(f"  - Skipped (already reported): {len(skipped_books)}")
        
        # Log final sales data
        logging.info(f"Final sales data after processing approved releases: {sales_data}")
        logging.info("PROCESS APPROVED RELEASES FUNCTION COMPLETED")
        logging.info("=" * 50)
        
    except Exception as e:
        logging.error(f"Unexpected error in process_approved_releases: {e}")
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