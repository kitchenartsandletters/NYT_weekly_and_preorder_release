#!/usr/bin/env python
"""
Preorder History Tracker

This module tracks which preorders have been included in previous reports
to prevent duplicate reporting of the same quantities.
"""
import os
import json
import logging
from datetime import datetime

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_preorder_history(history_file=None):
    """
    Load preorder history from a JSON file
    
    Args:
        history_file: Path to the history JSON file
        
    Returns:
        dict: Preorder history data
    """
    if not history_file:
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    # Create default structure if file doesn't exist
    if not os.path.exists(history_file):
        logging.info(f"Preorder history file not found, creating new one: {history_file}")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        
        # Create empty history
        default_history = {
            "reported_preorders": [],
            "last_updated": datetime.now().isoformat()
        }
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(default_history, f, indent=2)
        
        return default_history
    
    # Load existing history
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        logging.info(f"Loaded preorder history with {len(history.get('reported_preorders', []))} records")
        return history
    except Exception as e:
        logging.error(f"Error loading preorder history: {e}")
        # Return empty history in case of error
        return {"reported_preorders": [], "last_updated": datetime.now().isoformat()}

def save_preorder_history(history_data, history_file=None):
    """
    Save preorder history to a JSON file
    
    Args:
        history_data: Preorder history data
        history_file: Path to the history JSON file
    """
    if not history_file:
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    
    # Update last_updated timestamp
    history_data['last_updated'] = datetime.now().isoformat()
    
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=2)
        
        logging.info(f"Saved preorder history with {len(history_data.get('reported_preorders', []))} records")
    except Exception as e:
        logging.error(f"Error saving preorder history: {e}")

def is_preorder_reported(isbn, history_data):
    """
    Check if a preorder has already been reported
    
    Args:
        isbn: ISBN of the book
        history_data: Preorder history data
        
    Returns:
        tuple: (bool, dict) - Whether the preorder has been reported and the record if found
    """
    reported_preorders = history_data.get('reported_preorders', [])
    
    for record in reported_preorders:
        if record.get('isbn') == isbn:
            return True, record
    
    return False, None

def add_to_preorder_history(isbn, quantity, report_date=None, history_data=None, history_file=None):
    """
    Add a preorder to the history
    
    Args:
        isbn: ISBN of the book
        quantity: Quantity reported
        report_date: Date when reported (defaults to today)
        history_data: Preorder history data (will load if not provided)
        history_file: Path to the history JSON file
    """
    if not report_date:
        report_date = datetime.now().strftime('%Y-%m-%d')
    
    if not history_data:
        history_data = load_preorder_history(history_file)
    
    # Check if ISBN already exists
    is_reported, existing_record = is_preorder_reported(isbn, history_data)
    
    if is_reported:
        # Update existing record with additional information
        existing_record['quantity'] = quantity
        existing_record['report_date'] = report_date
        existing_record['last_updated'] = datetime.now().isoformat()
        logging.info(f"Updated history for ISBN {isbn} with quantity {quantity}")
    else:
        # Add new record
        new_record = {
            'isbn': isbn,
            'quantity': quantity,
            'report_date': report_date,
            'added': datetime.now().isoformat()
        }
        
        history_data['reported_preorders'].append(new_record)
        logging.info(f"Added new history record for ISBN {isbn} with quantity {quantity}")
    
    # Save updated history
    save_preorder_history(history_data, history_file)
    
    return history_data

def batch_add_to_history(preorders, report_date=None, history_file=None):
    """
    Add multiple preorders to the history in a batch
    
    Args:
        preorders: List of dicts with 'isbn' and 'quantity' keys
        report_date: Date when reported (defaults to today)
        history_file: Path to the history JSON file
        
    Returns:
        Updated history data
    """
    if not preorders:
        logging.warning("batch_add_to_history called with empty preorders list")
        return None
    
    if not report_date:
        report_date = datetime.now().strftime('%Y-%m-%d')
    
    # Set default history file path if not provided
    if not history_file:
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    # Make sure the directory exists
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    
    # Load existing history data
    history_data = None
    try:
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            # Verify structure
            if not isinstance(history_data, dict) or 'reported_preorders' not in history_data:
                logging.warning("Invalid history file structure, creating new")
                history_data = None
        
    except Exception as e:
        logging.error(f"Error loading history file: {e}")
        # Continue with empty history data
    
    # Create default history data if not loaded
    if not history_data:
        history_data = {
            "reported_preorders": [],
            "last_updated": datetime.now().isoformat()
        }
    
    # Keep track of updates
    added_count = 0
    updated_count = 0
    
    # Process each preorder
    for preorder in preorders:
        isbn = preorder.get('isbn')
        quantity = preorder.get('quantity', 0)
        title = preorder.get('title', 'Unknown Title')
        
        if not isbn:
            logging.warning(f"Skipping preorder with missing ISBN: {preorder}")
            continue
        
        try:
            quantity_int = int(quantity)
        except (ValueError, TypeError):
            logging.warning(f"Invalid quantity for ISBN {isbn}: {quantity}")
            quantity_int = 0
        
        if quantity_int <= 0:
            logging.warning(f"Skipping preorder with zero or negative quantity: ISBN {isbn}, quantity {quantity}")
            continue
        
        # Check if already reported
        already_reported = False
        for existing in history_data['reported_preorders']:
            if existing.get('isbn') == isbn:
                already_reported = True
                # Update existing record
                existing['quantity'] = quantity_int
                existing['report_date'] = report_date
                existing['title'] = title
                existing['last_updated'] = datetime.now().isoformat()
                updated_count += 1
                logging.info(f"Updated existing record for ISBN {isbn}")
                break
        
        # Add new record if not found
        if not already_reported:
            history_data['reported_preorders'].append({
                'isbn': isbn,
                'quantity': quantity_int,
                'title': title,
                'report_date': report_date,
                'added': datetime.now().isoformat()
            })
            added_count += 1
            logging.info(f"Added new record for ISBN {isbn}")
    
    # Update the last_updated timestamp
    history_data['last_updated'] = datetime.now().isoformat()
    
    # Save the updated history data
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=2)
        logging.info(f"Successfully saved preorder history with {len(history_data['reported_preorders'])} entries")
        logging.info(f"Added {added_count} new entries, updated {updated_count} existing entries")
        return history_data
    except Exception as e:
        logging.error(f"Error saving preorder history: {e}")
        return None

def initialize_history_with_reported_preorders(preorders, report_date, history_file=None):
    """
    Initialize the history file with preorders that have already been reported
    
    Args:
        preorders: List of dicts with 'isbn' and 'quantity' keys
        report_date: Date when the preorders were reported
        history_file: Path to the history JSON file
    """
    logging.info(f"Initializing preorder history with {len(preorders)} previously reported preorders")
    return batch_add_to_history(preorders, report_date, history_file)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    # Example usage
    sample_preorders = [
        {'isbn': '9780123456789', 'quantity': 5},
        {'isbn': '9780987654321', 'quantity': 12}
    ]
    
    history = initialize_history_with_reported_preorders(
        sample_preorders, 
        '2025-03-08'
    )
    
    print(json.dumps(history, indent=2))