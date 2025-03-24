#!/usr/bin/env python
"""
Repair Preorder History

This script checks the preorder history file for test data or corrupted entries 
and repairs it by removing any suspicious entries.
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Base directory for the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def repair_preorder_history(history_file=None, test_isbns=None, dry_run=False):
    """
    Repair the preorder history file by removing test data or corrupted entries
    
    Args:
        history_file: Path to the history file (default: preorders/preorder_history.json)
        test_isbns: List of ISBNs to remove (if None, use known test ISBNs)
        dry_run: If True, don't modify the file, just report what would be done
        
    Returns:
        Tuple of (success, removed_entries)
    """
    if history_file is None:
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    if not os.path.exists(history_file):
        logging.error(f"History file not found: {history_file}")
        return False, []
    
    # Default test ISBNs
    if test_isbns is None:
        test_isbns = [
            '9780262551311',  # Modern Chinese Foodways (test)
            '9784756256522',  # Fishes of Edo (test)
            '9781234567890'   # New Book Not In History (test)
        ]
        logging.info(f"Using default test ISBNs: {test_isbns}")
    
    try:
        # Read the history file
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        
        if 'reported_preorders' not in history_data or not isinstance(history_data['reported_preorders'], list):
            logging.error("Invalid history file structure")
            return False, []
        
        # Create backup
        backup_file = f"{history_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=2)
        logging.info(f"Created backup: {backup_file}")
        
        # Filter out test entries
        original_entries = history_data['reported_preorders']
        filtered_entries = [entry for entry in original_entries 
                           if entry.get('isbn') not in test_isbns]
        
        removed_entries = [entry for entry in original_entries 
                          if entry.get('isbn') in test_isbns]
        
        if not removed_entries:
            logging.info("No test entries found in history file")
            return True, []
        
        logging.info(f"Found {len(removed_entries)} test entries to remove")
        for entry in removed_entries:
            logging.info(f"  - ISBN: {entry.get('isbn')}, Title: {entry.get('title', 'Unknown')}, "
                        f"Quantity: {entry.get('quantity')}, Reported: {entry.get('report_date')}")
        
        if dry_run:
            logging.info("Dry run mode - not modifying file")
            return True, removed_entries
        
        # Update history data
        history_data['reported_preorders'] = filtered_entries
        history_data['last_updated'] = datetime.now().isoformat()
        
        # Write updated file
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=2)
        
        logging.info(f"Successfully removed {len(removed_entries)} test entries")
        logging.info(f"History file now contains {len(filtered_entries)} valid entries")
        
        return True, removed_entries
    
    except Exception as e:
        logging.error(f"Error repairing history file: {e}")
        return False, []

def main():
    """Main function to run the script"""
    parser = argparse.ArgumentParser(description='Repair preorder history file')
    parser.add_argument('--history-file', help='Path to history file (default: preorders/preorder_history.json)')
    parser.add_argument('--isbns', nargs='+', help='Specific ISBNs to remove')
    parser.add_argument('--dry-run', action='store_true', help='Don\'t modify the file, just report what would be done')
    args = parser.parse_args()
    
    success, removed_entries = repair_preorder_history(args.history_file, args.isbns, args.dry_run)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())