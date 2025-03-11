#!/usr/bin/env python
"""
Process approved releases for the weekly sales report

This module provides functions to include approved preorder titles in the weekly sales report
"""
import os
import json
import logging
from datetime import datetime

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
    """
    Process approved releases and add to sales data
    
    Args:
        sales_data: Dictionary mapping ISBNs to quantities
        base_dir: Base directory of the project
        
    Returns:
        Updated sales data with approved releases included
    """
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
        
        # Add approved books to sales data
        for book in approved_books:
            isbn = book.get('isbn')
            quantity = book.get('quantity', 0)
            
            if isbn and quantity > 0:
                sales_data[isbn] = sales_data.get(isbn, 0) + quantity
                logging.info(f"Added {quantity} copies of ISBN {isbn} from approved releases")
        
        # Mark file as processed
        processed_marker = approvals_file + '.processed'
        with open(processed_marker, 'w') as f:
            f.write(datetime.now().isoformat())
        
        logging.info(f"Marked approval file as processed: {processed_marker}")
        
    except Exception as e:
        logging.error(f"Error processing approved releases: {e}")
    
    return sales_data