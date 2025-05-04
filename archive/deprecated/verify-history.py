# DEPRECATED: This script is deprecated and will be removed in a future release.
#!/usr/bin/env python
"""
Verify Preorder History

This script verifies the integrity of the preorder history file and ensures it's properly structured.
It can repair common issues and display the current state of the preorder history tracking.
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

def verify_history_file(history_file=None, repair=False):
    """
    Verify the preorder history file structure and integrity
    
    Args:
        history_file: Path to the history file (default: preorders/preorder_history.json)
        repair: Whether to repair issues found
        
    Returns:
        Tuple of (is_valid, issues_found, issues_repaired)
    """
    if not history_file:
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    # Track issues
    issues_found = []
    issues_repaired = []
    
    # Check if file exists
    if not os.path.exists(history_file):
        issues_found.append("History file does not exist")
        
        if repair:
            try:
                # Create directory if needed
                os.makedirs(os.path.dirname(history_file), exist_ok=True)
                
                # Create empty history file
                default_history = {
                    "reported_preorders": [],
                    "last_updated": datetime.now().isoformat()
                }
                
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(default_history, f, indent=2)
                
                issues_repaired.append("Created new history file")
                logging.info(f"Created new history file: {history_file}")
            except Exception as e:
                logging.error(f"Failed to create history file: {e}")
                return False, issues_found, issues_repaired
    
    # Try to load the file
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        
        # Check structure
        if not isinstance(history_data, dict):
            issues_found.append("History data is not a dictionary")
            
            if repair:
                history_data = {
                    "reported_preorders": [],
                    "last_updated": datetime.now().isoformat()
                }
                issues_repaired.append("Repaired: Converted history data to dictionary")
        
        # Check for required keys
        for key in ["reported_preorders", "last_updated"]:
            if key not in history_data:
                issues_found.append(f"Missing required key: {key}")
                
                if repair:
                    if key == "reported_preorders":
                        history_data[key] = []
                    elif key == "last_updated":
                        history_data[key] = datetime.now().isoformat()
                    
                    issues_repaired.append(f"Repaired: Added missing key {key}")
        
        # Check reported_preorders type
        if "reported_preorders" in history_data and not isinstance(history_data["reported_preorders"], list):
            issues_found.append("'reported_preorders' is not a list")
            
            if repair:
                history_data["reported_preorders"] = []
                issues_repaired.append("Repaired: Converted 'reported_preorders' to list")
        
        # Check each preorder record
        if "reported_preorders" in history_data and isinstance(history_data["reported_preorders"], list):
            valid_preorders = []
            
            for i, preorder in enumerate(history_data["reported_preorders"]):
                preorder_issues = []
                
                # Check if it's a dictionary
                if not isinstance(preorder, dict):
                    preorder_issues.append(f"Preorder record {i} is not a dictionary")
                    continue
                
                # Check required fields
                for field in ["isbn", "quantity", "report_date"]:
                    if field not in preorder:
                        preorder_issues.append(f"Preorder record {i} missing field: {field}")
                
                # Check ISBN format
                if "isbn" in preorder and not str(preorder["isbn"]).startswith(("978", "979")):
                    preorder_issues.append(f"Preorder record {i} has invalid ISBN format: {preorder['isbn']}")
                
                # Check quantity is a number
                if "quantity" in preorder:
                    try:
                        quantity = int(preorder["quantity"])
                        if quantity <= 0:
                            preorder_issues.append(f"Preorder record {i} has invalid quantity: {quantity}")
                    except (ValueError, TypeError):
                        preorder_issues.append(f"Preorder record {i} has non-integer quantity: {preorder['quantity']}")
                
                # Check date format
                if "report_date" in preorder:
                    try:
                        datetime.strptime(preorder["report_date"], "%Y-%m-%d")
                    except ValueError:
                        preorder_issues.append(f"Preorder record {i} has invalid date format: {preorder['report_date']}")
                
                # If there are issues with this preorder
                if preorder_issues:
                    for issue in preorder_issues:
                        issues_found.append(issue)
                else:
                    valid_preorders.append(preorder)
            
            # If repair and some preorders were invalid
            if repair and len(valid_preorders) != len(history_data["reported_preorders"]):
                history_data["reported_preorders"] = valid_preorders
                issues_repaired.append(f"Repaired: Removed {len(history_data['reported_preorders']) - len(valid_preorders)} invalid preorder records")
        
        # Save repaired file if needed
        if repair and issues_repaired:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=2)
            
            logging.info(f"Saved repaired history file: {history_file}")
        
        # Return results
        is_valid = len(issues_found) == 0
        return is_valid, issues_found, issues_repaired
    
    except json.JSONDecodeError:
        issues_found.append("History file is not valid JSON")
        
        if repair:
            try:
                default_history = {
                    "reported_preorders": [],
                    "last_updated": datetime.now().isoformat()
                }
                
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(default_history, f, indent=2)
                
                issues_repaired.append("Repaired: Created new history file with default structure")
                logging.info(f"Created new history file with default structure: {history_file}")
            except Exception as e:
                logging.error(f"Failed to repair history file: {e}")
        
        return False, issues_found, issues_repaired
    
    except Exception as e:
        issues_found.append(f"Error reading history file: {e}")
        return False, issues_found, issues_repaired

def check_approved_releases(base_dir=None):
    """
    Check for recent approved releases files and their processing status
    """
    if not base_dir:
        base_dir = BASE_DIR
    
    output_dir = os.path.join(base_dir, 'output')
    
    if not os.path.exists(output_dir):
        logging.warning(f"Output directory does not exist: {output_dir}")
        return
    
    # Find approved_releases files
    approval_files = [f for f in os.listdir(output_dir) if f.startswith('approved_releases_') and f.endswith('.json')]
    
    if not approval_files:
        logging.info("No approved releases files found")
        return
    
    # Sort by filename (which contains date) to get the most recent
    approval_files.sort(reverse=True)
    
    logging.info(f"Found {len(approval_files)} approved releases files:")
    
    for file in approval_files:
        file_path = os.path.join(output_dir, file)
        processed_marker = file_path + '.processed'
        
        # Check if it's been processed
        processed = os.path.exists(processed_marker)
        
        # Try to read the file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            total_books = len(data.get('approved_releases', []))
            is_test_data = data.get('test_data', False)
            
            if processed:
                processed_time = datetime.fromtimestamp(os.path.getmtime(processed_marker)).isoformat()
                logging.info(f"  ✓ {file}: {total_books} books (Processed on {processed_time}){' TEST DATA' if is_test_data else ''}")
            else:
                logging.info(f"  ✗ {file}: {total_books} books (Not processed yet){' TEST DATA' if is_test_data else ''}")
        
        except Exception as e:
            logging.error(f"  ! {file}: Error reading file: {e}")

def check_for_duplicates(history_file=None):
    """
    Check for duplicate ISBNs in the preorder history
    """
    if not history_file:
        history_file = os.path.join(BASE_DIR, 'preorders', 'preorder_history.json')
    
    if not os.path.exists(history_file):
        logging.warning(f"History file does not exist: {history_file}")
        return
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        
        preorders = history_data.get('reported_preorders', [])
        
        # Check for duplicates
        isbn_counts = {}
        for preorder in preorders:
            isbn = preorder.get('isbn')
            if isbn:
                isbn_counts[isbn] = isbn_counts.get(isbn, 0) + 1
        
        duplicates = {isbn: count for isbn, count in isbn_counts.items() if count > 1}
        
        if duplicates:
            logging.warning(f"Found {len(duplicates)} duplicate ISBNs in history:")
            for isbn, count in duplicates.items():
                logging.warning(f"  ISBN {isbn}: {count} entries")
            
            # Get details of duplicates
            for isbn in duplicates:
                logging.info(f"Entries for ISBN {isbn}:")
                for i, preorder in enumerate(preorders):
                    if preorder.get('isbn') == isbn:
                        logging.info(f"  Entry {i}: Reported on {preorder.get('report_date')}, Quantity: {preorder.get('quantity')}")
        else:
            logging.info("No duplicate ISBNs found in history")
    
    except Exception as e:
        logging.error(f"Error checking for duplicates: {e}")

def main():
    """Main function to run the script"""
    parser = argparse.ArgumentParser(description='Verify preorder history integrity')
    parser.add_argument('--history-file', help='Path to history file (default: preorders/preorder_history.json)')
    parser.add_argument('--repair', action='store_true', help='Repair issues found in history file')
    parser.add_argument('--check-releases', action='store_true', help='Check approved releases files')
    parser.add_argument('--check-duplicates', action='store_true', help='Check for duplicate ISBNs in history')
    args = parser.parse_args()
    
    logging.info("Starting preorder history verification")
    
    # Verify history file
    is_valid, issues_found, issues_repaired = verify_history_file(args.history_file, args.repair)
    
    if is_valid:
        logging.info("✓ Preorder history file is valid")
    else:
        logging.warning("✗ Preorder history file has issues:")
        for issue in issues_found:
            logging.warning(f"  - {issue}")
        
        if issues_repaired:
            logging.info("Repairs made:")
            for repair in issues_repaired:
                logging.info(f"  + {repair}")
    
    # Check approved releases if requested
    if args.check_releases:
        logging.info("\nChecking approved releases files:")
        check_approved_releases()
    
    # Check for duplicates if requested
    if args.check_duplicates:
        logging.info("\nChecking for duplicate ISBNs in history:")
        check_for_duplicates(args.history_file)
    
    return 0 if is_valid else 1

if __name__ == "__main__":
    sys.exit(main())